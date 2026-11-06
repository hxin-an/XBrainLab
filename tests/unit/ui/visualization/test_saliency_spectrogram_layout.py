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
    assert top_row[1].x0 - top_row[0].x1 >= 6.0
    assert bottom_row[1].x0 - bottom_row[0].x1 >= 6.0

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


def test_spectrogram_cache_tracks_subject_selection(qtbot, monkeypatch):
    from dataclasses import replace

    from XBrainLab.backend.application import (
        SaliencyPlanIdentity,
        SaliencyRenderPublication,
        SaliencyRenderRequest,
        SaliencyRunIdentity,
    )
    from XBrainLab.backend.application.state import (
        SaliencyClassCoverageSnapshot,
        SaliencyMethodCoverageSnapshot,
    )

    view = SaliencySpectrogramWidget()
    qtbot.addWidget(view)
    view.set_saliency_coverage(
        SaliencyMethodCoverageSnapshot(
            method="Gradient",
            available=True,
            complete=True,
            classes=[
                SaliencyClassCoverageSnapshot(
                    class_index=0,
                    store_key=0,
                    display_name="left",
                    available=True,
                )
            ],
        )
    )
    figures = []
    monkeypatch.setattr(
        view, "_render_figure_async", lambda render, **_kwargs: figures.append(render())
    )
    base = _four_class_render_data()
    source = base.saliency_by_class[0]
    first, second = source[:2], source[2:] * 4
    request = SaliencyRenderRequest(
        publication_generation=1,
        run=SaliencyRunIdentity(SaliencyPlanIdentity(0), 0),
        method="Gradient",
    )
    outputs = []
    for subject, values in (
        (None, np.concatenate((first, second))),
        (10, first),
        (20, second),
        (None, np.concatenate((first, second))),
    ):
        data = replace(
            base,
            saliency_by_class={0: values},
            class_map=((0, "left"),),
            event_ids={"left": 0},
            subject_choices=((10, "Alice"), (20, "Bob")),
            selected_subject_id=subject,
        )
        view.invalidate_render_publication()
        view.update_plot(
            SaliencyRenderPublication(
                request=replace(request, subject_id=subject),
                generation=1,
                training_generation=1,
                data=data,
            ),
            False,
        )
        outputs.append(np.asarray(figures[-1].axes[0].images[0].get_array()).copy())
    assert not np.allclose(outputs[0], outputs[1])
    assert not np.allclose(outputs[1], outputs[2])
    np.testing.assert_array_equal(outputs[0], outputs[3])
    for figure in figures:
        figure.clear()


def test_qtagg_subplot_uses_available_area_at_native_dpi_after_resize(qtbot):
    from XBrainLab.ui.panels.visualization.saliency_views.base_saliency_view import (
        BaseSaliencyView,
    )

    view = BaseSaliencyView()
    qtbot.addWidget(view)
    view.resize(800, 550)
    view.show()
    qtbot.waitExposed(view)
    figure = Figure(figsize=(8, 5), dpi=100)
    axis = figure.add_subplot(111)
    axis.imshow(np.arange(640).reshape(4, 160), aspect="auto")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Channel")
    axis.set_title("Subject attribution")
    assert view._replace_figure(figure)
    for width in (800, 560, 800):
        view.resize(width, 550)
        qtbot.wait(30)
        canvas = view.canvas
        canvas.draw()
        renderer = canvas.get_renderer()
        assert canvas.device_pixel_ratio == pytest.approx(canvas.devicePixelRatioF())
        physical_width = canvas.width() * canvas.devicePixelRatioF()
        physical_height = canvas.height() * canvas.devicePixelRatioF()
        plot = axis.get_window_extent(renderer)
        labels = axis.get_tightbbox(renderer)
        assert plot.width >= physical_width * 0.70
        assert plot.height >= physical_height * 0.65
        assert labels.x0 >= -1
        assert labels.y0 >= -1
        assert labels.x1 <= physical_width + 1
        assert labels.y1 <= physical_height + 1


@pytest.mark.parametrize("pixel_ratio", (1.0, 1.25, 1.5, 2.0))
def test_agg_subplot_preserves_plot_area_at_scaled_pixel_ratio(pixel_ratio):
    figure = Figure(figsize=(8, 5), dpi=100)
    canvas = FigureCanvasAgg(figure)
    canvas._set_device_pixel_ratio(pixel_ratio)
    axis = figure.add_subplot(111)
    axis.imshow(np.arange(640).reshape(4, 160), aspect="auto")
    axis.set_xlabel("Time (s)")
    axis.set_ylabel("Channel")
    axis.set_title("Subject attribution")
    for width_inches in (8.0, 5.6, 8.0):
        figure.set_size_inches(width_inches, 5.5, forward=False)
        fit_figure_subplots_to_canvas(figure, canvas)
        canvas.draw()
        renderer = canvas.get_renderer()
        physical_width, physical_height = figure.get_size_inches() * figure.dpi
        plot = axis.get_window_extent(renderer)
        labels = axis.get_tightbbox(renderer)
        assert plot.width >= physical_width * 0.70
        assert plot.height >= physical_height * 0.65
        assert labels.x0 >= -1
        assert labels.y0 >= -1
        assert labels.x1 <= physical_width + 1
        assert labels.y1 <= physical_height + 1
    figure.clear()
