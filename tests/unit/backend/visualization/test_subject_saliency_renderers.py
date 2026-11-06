"""Numerical rendering of a subject with one missing trained class."""

from __future__ import annotations

import mne
import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy import signal

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.visualization.saliency_3d_engine import Saliency3DEngine
from XBrainLab.backend.visualization.saliency_map import SaliencyMapViz
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)
from XBrainLab.backend.visualization.saliency_topomap import SaliencyTopoMapViz


def _subject_data():
    names = ("C3", "C4", "Cz", "Fz", "Pz")
    positions = mne.channels.make_standard_montage("standard_1020").get_positions()[
        "ch_pos"
    ]
    time = np.arange(128) / 64.0
    waveform = (1.0 + np.arange(5)[:, None]) * (
        1.0 + 0.25 * np.sin(2 * np.pi * 8 * time)
    )
    source = np.stack((waveform, 3 * waveform, 100 * waveform))
    data = SaliencyRenderData(
        method="Gradient",
        saliency_by_class={0: np.empty((0, 5, 128)), 1: source[:2]},
        class_map=((769, "Absent class"), (770, "Selected class")),
        event_ids={"Absent class": 769, "Selected class": 770},
        channel_names=names,
        channel_positions=tuple(tuple(positions[name]) for name in names),
        sfreq=64.0,
        tmin=-0.25,
        subject_choices=((0, "Selected subject"), (1, "Other subject")),
        selected_subject_id=0,
    )
    return data, waveform, source


def _assert_visible_selected_class(fig):
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())
    assert np.ptp(rgba[:, :, :3]) > 0
    class_axes = [axis for axis in fig.axes if axis.images]
    assert len(class_axes) == 1
    assert class_axes[0].get_title() == "Selected class"
    image = class_axes[0].images[0]
    assert np.isfinite(image.get_array().compressed()).all()
    assert image.get_array().size > 0
    return image


def test_subject_channel_time_renders_only_available_class_trials():
    data, waveform, source = _subject_data()
    figure = SaliencyMapViz(data).get_plt("Gradient", absolute=False)
    image = _assert_visible_selected_class(figure)
    np.testing.assert_allclose(image.get_array(), 2 * waveform)
    np.testing.assert_array_equal(source[2], 100 * waveform)


def test_subject_spectrogram_renders_available_class_without_foreign_trials():
    data, waveform, _source = _subject_data()
    figure = SaliencySpectrogramMapViz(data).get_plt("Gradient")
    image = _assert_visible_selected_class(figure)
    # Linearity gives mean magnitude 2 * the one-trial magnitude, before
    # averaging channels. No attribution from the 100x foreign trial belongs here.
    _frequencies, _times, transformed = signal.stft(
        waveform,
        fs=64.0,
        nperseg=64,
        noverlap=32,
        boundary=None,
        padded=False,
    )
    np.testing.assert_allclose(
        image.get_array(),
        2 * np.abs(transformed).mean(axis=0),
        atol=1e-14,
    )


def test_subject_topomap_runs_real_interpolation_for_available_class(monkeypatch):
    data, waveform, _source = _subject_data()
    original = mne.viz.plot_topomap
    interpolated = []

    def capture_data(*args, **kwargs):
        interpolated.append(np.asarray(kwargs["data"]).copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(mne.viz, "plot_topomap", capture_data)
    figure = SaliencyTopoMapViz(data).get_plt("Gradient", absolute=False)
    image = _assert_visible_selected_class(figure)
    assert len(interpolated) == 1
    np.testing.assert_allclose(interpolated[0], (2 * waveform).mean(axis=1))
    assert image.get_clim() == pytest.approx((-10.0, 10.0))


def test_subject_3d_processes_real_mesh_and_scalars_without_foreign_trials():
    data, waveform, _source = _subject_data()
    engine = Saliency3DEngine()
    assert not engine.model_error
    assert engine.process_data(data, "Selected class") == 5
    np.testing.assert_allclose(engine.saliency, 2 * waveform)
    assert engine.saliency_cap.n_points > 0
    scalars = engine.update_scalars(17)
    assert scalars is not None
    assert scalars.shape == (engine.saliency_cap.n_points,)
    assert np.isfinite(scalars).all()
    expected = 2 * waveform[:, 17]
    assert scalars.min() >= expected.min() - 1e-10
    assert scalars.max() <= expected.max() + 1e-10
    with pytest.raises(KeyError, match="No saliency for selected class"):
        engine.process_data(data, "Absent class")


@pytest.mark.parametrize(
    "visualizer", [SaliencyMapViz, SaliencySpectrogramMapViz, SaliencyTopoMapViz]
)
def test_subject_missing_class_is_explicitly_unavailable_in_single_class_view(
    visualizer,
):
    data, _waveform, _source = _subject_data()
    with pytest.raises(ValueError, match="Selected saliency class is not available"):
        visualizer(data).get_plt(
            "Gradient", absolute=False, display_mode="single", selected_label_key=0
        )
