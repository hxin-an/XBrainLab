from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import XBrainLab.backend.visualization.saliency_3d_engine as saliency_3d_module
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine


class _EpochData:
    event_id: ClassVar[dict[str, int]] = {"left": 0, "right": 1}


class _OneBasedEpochData:
    event_id: ClassVar[dict[str, int]] = {"left": 1, "right": 2}


class _ChannelEpochData:
    event_id: ClassVar[dict[str, int]] = {"left": 0}

    def __init__(self, *, names_count: int, positions_count: int) -> None:
        self._names = [f"EEG{index}" for index in range(names_count)]
        self._positions = np.zeros((positions_count, 3), dtype=float)

    def get_channel_names(self) -> list[str]:
        return self._names

    def get_montage_position(self) -> np.ndarray:
        return self._positions


class _TimedEpochData(_ChannelEpochData):
    def __init__(
        self,
        *,
        sample_count: int,
        sfreq: float,
        tmin: float,
    ) -> None:
        super().__init__(names_count=1, positions_count=1)
        self._sample_count = sample_count
        self._sfreq = sfreq
        self.tmin = tmin

    def get_model_args(self) -> dict[str, float | int]:
        return {
            "n_classes": 1,
            "channels": 1,
            "samples": self._sample_count,
            "sfreq": self._sfreq,
        }


def _process_timed_saliency(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sample_count: int,
    sfreq: float,
    tmin: float,
) -> Saliency3DEngine:
    monkeypatch.setattr(Saliency3DEngine, "_load_models", lambda _self: None)
    saliency_cap = MagicMock()
    saliency_cap.scale.return_value = saliency_cap
    saliency_cap.n_points = 1
    monkeypatch.setattr(
        saliency_3d_module,
        "channel_convex_hull",
        lambda _positions: saliency_cap,
    )

    engine = Saliency3DEngine()
    engine.head_mesh = MagicMock()
    engine.head_mesh.bounds = (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    engine.brain_mesh = MagicMock()
    eval_record = type(
        "EvalRecord",
        (),
        {"gradient": {0: np.ones((2, 1, sample_count), dtype=float)}},
    )()
    epoch_data = _TimedEpochData(
        sample_count=sample_count,
        sfreq=sfreq,
        tmin=tmin,
    )

    engine.process_data(eval_record, epoch_data, "left")
    return engine


def test_3d_static_mesh_assets_are_loaded_and_scaled_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(Saliency3DEngine, "_load_models", lambda _self: None)
    head_path = tmp_path / "head.ply"
    brain_path = tmp_path / "brain.ply"
    head_path.write_bytes(b"head")
    brain_path.write_bytes(b"brain")

    head_mesh = MagicMock(name="head_mesh")
    brain_mesh = MagicMock(name="brain_mesh")
    head_scaled = MagicMock(name="head_scaled")
    brain_scaled_input = MagicMock(name="brain_scaled_input")
    brain_scaled = MagicMock(name="brain_scaled")
    head_mesh.copy.return_value.scale.return_value = head_scaled
    brain_mesh.copy.return_value.scale.return_value = brain_scaled_input
    brain_scaled_input.triangulate.return_value = brain_scaled

    Saliency3DEngine._clear_mesh_cache()
    try:
        with patch.object(
            saliency_3d_module.pv,
            "read",
            side_effect=[head_mesh, brain_mesh],
        ) as read:
            first = Saliency3DEngine(mesh_scale_scalar=0.8)
            first._init_meshes(str(tmp_path))
            second = Saliency3DEngine(mesh_scale_scalar=0.8)
            second._init_meshes(str(tmp_path))

        assert read.call_count == 2
        assert first.head_mesh is second.head_mesh is head_mesh
        assert first.brain_mesh is second.brain_mesh is brain_mesh
        assert first.head_scaled is second.head_scaled is head_scaled
        assert first.brain_scaled is second.brain_scaled is brain_scaled
        head_mesh.copy.assert_called_once()
        brain_mesh.copy.assert_called_once()
        assert len(Saliency3DEngine._mesh_cache) == 1
    finally:
        Saliency3DEngine._clear_mesh_cache()


def test_3d_mesh_cache_reloads_changed_assets_and_remains_bounded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(Saliency3DEngine, "_load_models", lambda _self: None)
    head_path = tmp_path / "head.ply"
    brain_path = tmp_path / "brain.ply"
    head_path.write_bytes(b"head")
    brain_path.write_bytes(b"brain")

    first_head = MagicMock(name="first_head")
    first_brain = MagicMock(name="first_brain")
    second_head = MagicMock(name="second_head")
    second_brain = MagicMock(name="second_brain")
    for mesh in (first_head, first_brain, second_head, second_brain):
        mesh.copy.return_value.scale.return_value.triangulate.return_value = MagicMock()

    Saliency3DEngine._clear_mesh_cache()
    try:
        with patch.object(
            saliency_3d_module.pv,
            "read",
            side_effect=[first_head, first_brain, second_head, second_brain],
        ) as read:
            first = Saliency3DEngine()
            first._init_meshes(str(tmp_path))
            head_path.write_bytes(b"changed-head")
            second = Saliency3DEngine()
            second._init_meshes(str(tmp_path))

        assert read.call_count == 4
        assert second.head_mesh is second_head
        assert second.head_mesh is not first.head_mesh
        assert len(Saliency3DEngine._mesh_cache) == 1
    finally:
        Saliency3DEngine._clear_mesh_cache()


def test_3d_saliency_key_resolution_does_not_confuse_one_based_event_codes_with_class_keys() -> (
    None
):
    saliency_store = {
        0: np.ones((2, 4, 32)),
        1: np.ones((2, 4, 32)) * 2,
    }

    left_key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _OneBasedEpochData(),
        "left",
    )
    right_key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _OneBasedEpochData(),
        "right",
    )

    assert left_key == 0
    assert right_key == 1


def test_3d_saliency_key_resolution_preserves_raw_event_code_keys() -> None:
    saliency_store = {
        1: np.ones((2, 4, 32)),
        2: np.ones((2, 4, 32)) * 2,
    }

    left_key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _OneBasedEpochData(),
        "left",
    )
    right_key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _OneBasedEpochData(),
        "right",
    )

    assert left_key == 1
    assert right_key == 2


def test_3d_saliency_key_resolution_does_not_substitute_another_class() -> None:
    saliency_store = {
        0: np.empty((0, 4, 32)),
        1: np.ones((2, 4, 32)),
    }

    with pytest.raises(KeyError, match="No saliency for selected class 'left'"):
        Saliency3DEngine._resolve_saliency_label_key(
            saliency_store,
            _EpochData(),
            "left",
        )


def test_3d_saliency_key_resolution_requires_nonempty_saliency_data() -> None:
    saliency_store = {0: np.empty((0, 4, 32))}

    with pytest.raises(KeyError, match="No saliency for selected class 'left'"):
        Saliency3DEngine._resolve_saliency_label_key(
            saliency_store,
            _EpochData(),
            "left",
        )


def test_3d_saliency_key_resolution_preserves_stringified_class_keys() -> None:
    saliency_store = {
        "0": np.ones((2, 4, 32)),
        "1": np.ones((2, 4, 32)) * 2,
    }

    key = Saliency3DEngine._resolve_saliency_label_key(
        saliency_store,
        _EpochData(),
        "right",
    )

    assert key == "1"


@pytest.mark.parametrize(
    ("names_count", "positions_count", "saliency_channels"),
    [
        (4, 3, 4),
        (3, 4, 4),
        (4, 4, 3),
    ],
)
def test_3d_process_data_rejects_channel_identity_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    names_count: int,
    positions_count: int,
    saliency_channels: int,
) -> None:
    monkeypatch.setattr(Saliency3DEngine, "_load_models", lambda _self: None)
    engine = Saliency3DEngine()
    eval_record = type(
        "EvalRecord",
        (),
        {"gradient": {0: np.ones((2, saliency_channels, 32))}},
    )()
    epoch_data = _ChannelEpochData(
        names_count=names_count,
        positions_count=positions_count,
    )

    with pytest.raises(ValueError, match="3D channel identity mismatch"):
        engine.process_data(eval_record, epoch_data, "left")

    assert engine.saliency is None


def test_3d_time_axis_uses_epoch_tmin_and_sampling_frequency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _process_timed_saliency(
        monkeypatch,
        sample_count=4,
        sfreq=8.0,
        tmin=-0.25,
    )

    np.testing.assert_allclose(
        engine.time_axis_seconds,
        np.array([-0.25, -0.125, 0.0, 0.125]),
    )
    assert engine.time_range_seconds == pytest.approx((-0.25, 0.125))
    assert engine.sample_index_for_time(-10.0) == 0
    assert engine.sample_index_for_time(-0.13) == 1
    assert engine.sample_index_for_time(-0.06) == 2
    assert engine.sample_index_for_time(10.0) == 3


def test_3d_time_axis_supports_single_sample_negative_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _process_timed_saliency(
        monkeypatch,
        sample_count=1,
        sfreq=256.0,
        tmin=-0.75,
    )

    np.testing.assert_allclose(engine.time_axis_seconds, np.array([-0.75]))
    assert engine.time_range_seconds == pytest.approx((-0.75, -0.75))
    assert engine.sample_index_for_time(-100.0) == 0
    assert engine.sample_index_for_time(100.0) == 0
