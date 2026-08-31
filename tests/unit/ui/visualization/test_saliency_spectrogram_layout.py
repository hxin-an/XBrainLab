from __future__ import annotations

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)
from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
    fit_figure_subplots_to_canvas,
)
from XBrainLab.ui.panels.visualization.saliency_views.spectrogram_view import (
    SaliencySpectrogramWidget,
)


def _four_class_render_data() -> SaliencyRenderData:
    rng = np.random.default_rng(43)
    return SaliencyRenderData(
        method="Gradient",
        saliency_by_class={
            label: rng.standard_normal((4, 4, 64), dtype=np.float32)
            for label in range(4)
        },
        class_map=tuple((label, f"class-{label}") for label in range(4)),
        event_ids={f"class-{label}": label for label in range(4)},
        channel_names=("C3", "C4", "Cz", "Pz"),
        channel_positions=(
            (-0.04, 0.0, 0.08),
            (0.04, 0.0, 0.08),
            (0.0, 0.03, 0.09),
            (0.0, -0.04, 0.07),
        ),
        sfreq=128.0,
        tmin=-0.2,
    )


def _four_class_spectrogram() -> Figure:
    return SaliencySpectrogramMapViz(_four_class_render_data()).get_plt(
        method="Gradient",
    )


def _subplot_margins(figure: Figure) -> tuple[float, float, float, float]:
    params = figure.subplotpars
    return (params.left, params.right, params.bottom, params.top)


def test_four_class_spectrogram_uses_scrollable_minimum_height(qtbot) -> None:
    """Compact overview keeps both rows readable instead of compressing them."""
    view = SaliencySpectrogramWidget()
    qtbot.addWidget(view)
    figure = _four_class_spectrogram()

    assert view._canvas_scroll_area is not None
    assert getattr(figure, "_xbrainlab_min_canvas_height", 0) == 480


def test_compact_spectrogram_viewport_preserves_rows_and_one_live_canvas(qtbot) -> None:
    """Panel returns, resizes, and rerenders retain one readable plot surface."""
    view = SaliencySpectrogramWidget()
    qtbot.addWidget(view)
    view.resize(500, 300)
    view.show()
    qtbot.waitExposed(view)

    assert view._replace_figure(_four_class_spectrogram()) is True
    qtbot.waitUntil(
        lambda: view._canvas_scroll_area is not None
        and view._canvas_scroll_area.verticalScrollBar().maximum() > 0,
    )
    assert view.canvas is not None
    assert view.canvas.minimumHeight() == 480
    initial_generation = view._plot_generation
    view.canvas.draw()
    renderer = view.canvas.get_renderer()
    bounds = [axis.get_tightbbox(renderer) for axis in view.fig.axes[:4]]
    assert all(bound is not None for bound in bounds)
    top_row = [bound for bound in bounds[:2] if bound is not None]
    bottom_row = [bound for bound in bounds[2:] if bound is not None]
    assert min(bound.y0 for bound in top_row) > max(bound.y1 for bound in bottom_row)

    view.hide()
    qtbot.wait(0)
    view.show()
    view.resize(640, 480)
    qtbot.wait(0)
    view.resize(500, 300)
    qtbot.wait(0)
    assert view._plot_generation == initial_generation
    assert len(view.findChildren(FigureCanvas)) == 1

    assert view._replace_figure(_four_class_spectrogram()) is True
    qtbot.wait(0)
    assert len(view.findChildren(FigureCanvas)) == 1


def test_compact_spectrogram_width_keeps_colorbar_outside_data_axes() -> None:
    """The colorbar must own a column instead of consuming the final tile."""
    figure = _four_class_spectrogram()
    figure.set_size_inches(5.0, 4.8, forward=True)
    canvas = FigureCanvasAgg(figure)

    fit_figure_subplots_to_canvas(figure, canvas)
    canvas.draw()
    renderer = canvas.get_renderer()
    data_bounds = [axis.get_tightbbox(renderer) for axis in figure.axes[:-1]]
    colorbar_bounds = figure.axes[-1].get_tightbbox(renderer)

    assert colorbar_bounds is not None
    assert all(bounds is not None for bounds in data_bounds)
    assert (
        max(bounds.x1 for bounds in data_bounds if bounds is not None)
        < colorbar_bounds.x0
    )


def test_figure_fit_recovers_authored_layout_after_compact_resize() -> None:
    """A compact resize cannot permanently compound a figure's margins."""
    compact_figure = Figure(figsize=(5.0, 4.8), dpi=100)
    compact_axis = compact_figure.add_subplot(111)
    compact_axis.set_ylabel("Frequency (Hz)")
    compact_figure.subplots_adjust(left=0.10, right=0.86, bottom=0.12, top=0.92)
    compact_canvas = FigureCanvasAgg(compact_figure)

    fit_figure_subplots_to_canvas(compact_figure, compact_canvas)
    compact_figure.set_size_inches(9.0, 4.8, forward=True)
    fit_figure_subplots_to_canvas(compact_figure, compact_canvas)

    fresh_figure = Figure(figsize=(9.0, 4.8), dpi=100)
    fresh_axis = fresh_figure.add_subplot(111)
    fresh_axis.set_ylabel("Frequency (Hz)")
    fresh_figure.subplots_adjust(left=0.10, right=0.86, bottom=0.12, top=0.92)
    fresh_canvas = FigureCanvasAgg(fresh_figure)
    fit_figure_subplots_to_canvas(fresh_figure, fresh_canvas)

    assert _subplot_margins(compact_figure) == pytest.approx(
        _subplot_margins(fresh_figure),
    )
