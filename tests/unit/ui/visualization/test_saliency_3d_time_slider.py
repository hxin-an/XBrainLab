from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np

from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_head import Saliency3D


class _PlotterStub:
    def __init__(self) -> None:
        self.slider_kwargs: dict[str, Any] = {}
        self.camera = MagicMock()

    def add_camera_orientation_widget(self) -> None:
        pass

    def add_slider_widget(self, **kwargs: Any) -> None:
        self.slider_kwargs = kwargs

    def add_checkbox_button_widget(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def add_text(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def add_mesh(self, *_args: Any, **_kwargs: Any) -> object:
        return object()

    def add_scalar_bar(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def update_scalar_bar_range(self, *_args: Any, **_kwargs: Any) -> None:
        pass


def _saliency_with_time_axis() -> tuple[
    Saliency3D,
    _PlotterStub,
    MagicMock,
    MagicMock,
]:
    saliency = Saliency3D.__new__(Saliency3D)
    saliency_any = cast(Any, saliency)
    engine = MagicMock()
    engine.saliency = np.zeros((3, 3))
    engine.saliency_cap = object()
    engine.brain_scaled = object()
    engine.scalar_bar_range = [0.0, 1.0]
    engine.time_range_seconds = (-0.2, 0.0)
    engine.initial_time_seconds = -0.2
    engine.sample_index_for_time.return_value = 2
    plotter = _PlotterStub()
    update = MagicMock()
    saliency_any.engine = engine
    saliency_any.plotter = plotter
    saliency_any.channelBox = MagicMock()
    saliency_any.headBox = MagicMock()
    saliency_any.showChannel = True
    saliency_any.showHead = True
    saliency_any.chs = []
    saliency_any.cmap = "coolwarm"
    saliency_any.param = {"sample_index": 0, "save": False}
    saliency_any.update = update
    return saliency, plotter, engine, update


def test_3d_scene_has_no_overlay_slider_and_accepts_epoch_time_seconds() -> None:
    saliency, plotter, engine, update = _saliency_with_time_axis()

    saliency.get_3d_head_plot()

    # The Qt view owns the visible ``Epoch time (s)`` control.  Keeping the
    # PyVista canvas free of overlays prevents controls and labels from
    # covering the saliency surface.
    assert plotter.slider_kwargs == {}

    saliency._set_time_seconds(-0.04)

    engine.sample_index_for_time.assert_called_once_with(-0.04)
    assert saliency.param["sample_index"] == 2
    update.assert_called_once_with()
