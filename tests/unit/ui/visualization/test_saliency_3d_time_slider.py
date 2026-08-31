from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import numpy as np
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QLabel, QWidget

from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_head import Saliency3D
from XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view import (
    Saliency3DPlotWidget,
)
from XBrainLab.ui.styles.theme import Theme


def _new_widget(qtbot, monkeypatch) -> Saliency3DPlotWidget:
    monkeypatch.setattr(
        "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view."
        "Saliency3DPlotWidget._active_qt_platform_name",
        staticmethod(lambda: "offscreen"),
    )
    widget = Saliency3DPlotWidget(parent=None)
    qtbot.addWidget(widget)
    return widget


def test_initial_3d_prompt_uses_warning_color(qtbot, monkeypatch) -> None:
    widget = _new_widget(qtbot, monkeypatch)

    prompt = next(
        label
        for label in widget.findChildren(QLabel)
        if label.text() == "Select a fold and method to visualize"
    )

    assert "color: " + Theme.WARNING in prompt.styleSheet()


class _PlotterStub:
    def __init__(self) -> None:
        self.slider_kwargs: dict[str, Any] = {}
        self.scalar_bar_args: tuple[Any, ...] = ()
        self.scalar_bar_kwargs: dict[str, Any] = {}
        self.camera = MagicMock()

    def add_camera_orientation_widget(self) -> None:
        pass

    def clear_camera_widgets(self) -> None:
        pass

    def add_slider_widget(self, **kwargs: Any) -> None:
        self.slider_kwargs = kwargs

    def add_checkbox_button_widget(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def add_text(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def add_mesh(self, *_args: Any, **_kwargs: Any) -> object:
        return object()

    def add_scalar_bar(self, *args: Any, **kwargs: Any) -> None:
        self.scalar_bar_args = args
        self.scalar_bar_kwargs = kwargs

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
    assert plotter.scalar_bar_args == ("saliency",)
    assert plotter.scalar_bar_kwargs["position_x"] == 0.1
    assert plotter.scalar_bar_kwargs["width"] == 0.8
    assert (
        plotter.scalar_bar_kwargs["position_x"] + plotter.scalar_bar_kwargs["width"] / 2
        == 0.5
    )

    saliency._set_time_seconds(-0.04)

    engine.sample_index_for_time.assert_called_once_with(-0.04)
    assert saliency.param["sample_index"] == 2
    update.assert_called_once_with()


def test_epoch_time_controls_fill_available_width_at_wide_and_narrow_widths(
    qtbot,
    monkeypatch,
) -> None:
    widget = _new_widget(qtbot, monkeypatch)
    widget.scene_controls.show()

    time_label = widget.epoch_time_label
    time_spin = widget.epoch_time_spin

    for width in (1180, 800):
        widget.resize(width, 600)
        widget.show()
        QApplication.processEvents()

        assert time_label.parentWidget() is widget.scene_controls
        assert widget.time_slider.parentWidget() is widget.scene_controls
        assert time_spin.parentWidget() is widget.scene_controls
        assert time_label.geometry().left() == 8
        assert time_label.geometry().right() < widget.time_slider.geometry().left()
        assert widget.time_slider.geometry().right() < time_spin.geometry().left()
        assert widget.scene_controls.width() - time_spin.geometry().right() - 1 == 8
        assert widget.time_slider.width() >= width - 280


def _ready_time_scene(time_axis: np.ndarray) -> MagicMock:
    engine = MagicMock()
    engine.time_axis_seconds = time_axis
    engine.time_range_seconds = (float(time_axis[0]), float(time_axis[-1]))
    engine.initial_time_seconds = float(time_axis[0])
    engine.sample_index_for_time.side_effect = lambda value: int(
        np.abs(time_axis - float(value)).argmin()
    )
    scene = MagicMock()
    scene.engine = engine
    return scene


def test_epoch_time_spin_tracks_slider_and_nearest_sample(qtbot, monkeypatch) -> None:
    widget = _new_widget(qtbot, monkeypatch)
    scene = _ready_time_scene(np.array([-0.25, -0.125, 0.0, 0.125]))

    widget._saliency_scene = scene
    widget._configure_epoch_time_controls()
    widget.scene_controls.show()
    widget.resize(900, 600)
    widget.show()
    QApplication.processEvents()

    spin = widget.epoch_time_spin
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.isVisible()
    assert spin.keyboardTracking() is False
    assert spin.minimum() == -0.25
    assert spin.maximum() == 0.125
    assert spin.singleStep() == 0.125
    assert spin.decimals() == 3
    assert spin.value() == -0.25

    widget.time_slider.setValue(700)

    scene._set_time_seconds.assert_called_once_with(0.0)
    assert spin.value() == 0.0

    scene._set_time_seconds.reset_mock()
    spin.setValue(-0.13)

    scene._set_time_seconds.assert_called_once_with(-0.125)
    assert spin.value() == -0.125


def test_epoch_time_controls_reset_for_replaced_or_single_sample_scene(
    qtbot,
    monkeypatch,
) -> None:
    widget = _new_widget(qtbot, monkeypatch)
    first_scene = _ready_time_scene(np.array([-0.25, -0.125, 0.0, 0.125]))
    single_sample_scene = _ready_time_scene(np.array([-0.75]))

    widget._saliency_scene = first_scene
    widget._configure_epoch_time_controls()
    widget.epoch_time_spin.setValue(0.125)
    widget._saliency_scene = single_sample_scene
    widget._configure_epoch_time_controls()

    assert widget.epoch_time_spin.minimum() == -0.75
    assert widget.epoch_time_spin.maximum() == -0.75
    assert widget.epoch_time_spin.value() == -0.75
    assert widget.epoch_time_spin.isEnabled() is False
    assert widget.time_slider.isEnabled() is False


def test_epoch_time_spin_changes_only_the_existing_scene_time(
    qtbot, monkeypatch
) -> None:
    widget = _new_widget(qtbot, monkeypatch)
    scene = _ready_time_scene(np.array([-0.25, -0.125, 0.0, 0.125]))
    widget._saliency_scene = scene
    widget._configure_epoch_time_controls()
    widget.plotter_widget = MagicMock()

    widget.epoch_time_spin.setValue(0.125)

    scene._set_time_seconds.assert_called_once_with(0.125)
    assert widget._engine_worker is None
    widget.plotter_widget.reset_camera.assert_not_called()


def test_completed_3d_scene_resets_time_controls_from_its_engine(
    qtbot,
    monkeypatch,
) -> None:
    widget = _new_widget(qtbot, monkeypatch)
    scene = _ready_time_scene(np.array([-0.75, -0.5, -0.25]))
    widget.plotter_widget = QWidget()

    class SceneWithTimedEngine:
        init_error = ""

        def __init__(self, *_args, **_kwargs) -> None:
            self.engine = scene.engine

        def get_3d_head_plot(self) -> None:
            pass

        def _set_time_seconds(self, value: float) -> None:
            scene._set_time_seconds(value)

    with patch(
        "XBrainLab.ui.panels.visualization.saliency_views.plot_3d_view.Saliency3D",
        SceneWithTimedEngine,
    ):
        widget._do_3d_plot(MagicMock(), "left")

    assert widget.scene_controls.isHidden() is False
    assert widget.epoch_time_spin.minimum() == -0.75
    assert widget.epoch_time_spin.maximum() == -0.25
    assert widget.epoch_time_spin.value() == -0.75
