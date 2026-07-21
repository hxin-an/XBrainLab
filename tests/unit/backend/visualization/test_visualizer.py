from unittest.mock import patch

import mne
import numpy as np
import pytest
from matplotlib import pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy import signal

from XBrainLab.backend.dataset import Epochs
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.training.record import EvalRecord
from XBrainLab.backend.training.record.eval import SaliencyProducerIdentity
from XBrainLab.backend.training.saliency_artifact_integrity import (
    SaliencyArtifactIntegrityError,
    SaliencyIntegrityReason,
)
from XBrainLab.backend.visualization import VisualizerType

epoch_duration = 3
n_trial = 3
fs = 5
subject_list = ["1", "2", "3"]
session_list = ["1", "2"]
ch_names = ["O1", "O2"]


def get_preprocessed_data_list(n_class):
    event_id = {"c" + str(i): i for i in range(n_class)}
    events = np.zeros((n_class * n_trial, 3), dtype=int)
    events[:, 0] = np.arange(events.shape[0])
    events[:, 2] = np.arange(n_class).repeat(n_trial)

    ch_types = "eeg"

    result = []
    for subject in subject_list:
        for session in session_list:
            base = int(subject) * 100000 + int(session) * 1000
            info = mne.create_info(ch_names=ch_names, sfreq=fs, ch_types=ch_types)
            data = np.zeros((len(events), len(ch_names), epoch_duration * fs))
            for i in range(len(events)):
                data[i, :, :] = base + events[i, 0]
            epochs = mne.EpochsArray(
                data, info, events=events, tmin=0, event_id=event_id
            )
            raw = Raw(f"test/sub-{subject}_ses-{session}.fif", epochs)
            raw.set_subject_name(subject)
            raw.set_session_name(session)
            result.append(raw)
    return result


def get_abs_visualizer():
    return [
        VisualizerType.SaliencyMap,
        VisualizerType.SaliencyTopoMap,
    ]


def get_remaining_visualizer():
    abs_visualizer = get_abs_visualizer()
    all_visualizer = [i for i in VisualizerType if i not in abs_visualizer]
    return all_visualizer


def _bound_eval_record(epochs, *args) -> EvalRecord:
    """Build saliency test data through the producer identity boundary."""
    method_stores = dict(
        zip(
            (
                "Gradient",
                "Gradient * Input",
                "SmoothGrad",
                "SmoothGrad_Squared",
                "VarGrad",
            ),
            args[2:],
            strict=True,
        )
    )
    active_methods = {method for method, store in method_stores.items() if store}
    record = EvalRecord(
        *args,
        saliency_method_parameters={method: {} for method in active_methods},
        saliency_noise_seeds={
            method: 1
            for method in active_methods
            if method in {"SmoothGrad", "SmoothGrad_Squared", "VarGrad"}
        },
    )
    record.bind_saliency_context(
        epochs,
        producer_identity=SaliencyProducerIdentity.from_components(
            dataset={"name": "visualizer"},
            split={"name": "visualizer"},
            run={"name": "visualizer"},
            model={"name": "visualizer"},
        ),
    )
    return record


@pytest.mark.parametrize("absolute", [True, False])
@pytest.mark.parametrize(
    "epochs, n_class",
    [
        (Epochs(get_preprocessed_data_list(2)), 2),
        (Epochs(get_preprocessed_data_list(3)), 3),
        (Epochs(get_preprocessed_data_list(4)), 4),
    ],
)
@pytest.mark.parametrize("visualizer", get_abs_visualizer())
@pytest.mark.parametrize("mask_out", [True, False])
def test_map(absolute, epochs, n_class, visualizer, mask_out):
    label = np.ones(10)
    output = np.ones((10, n_class))
    gradient = {i: np.zeros((10, 2, 4)) for i in range(n_class)}
    if mask_out:
        gradient[0] = np.array([])
    epochs.set_channels(ch_names, np.random.rand(len(ch_names), 3))

    # Create dummy data for new EvalRecord arguments
    gradient_input = gradient.copy()
    smoothgrad = gradient.copy()
    smoothgrad_sq = gradient.copy()
    vargrad = gradient.copy()

    if mask_out:
        with pytest.raises(SaliencyArtifactIntegrityError) as error:
            _bound_eval_record(
                epochs,
                label,
                output,
                gradient,
                gradient_input,
                smoothgrad,
                smoothgrad_sq,
                vargrad,
            )
        assert error.value.reason is SaliencyIntegrityReason.PARTIAL_COVERAGE
        return
    eval_record = _bound_eval_record(
        epochs,
        label,
        output,
        gradient,
        gradient_input,
        smoothgrad,
        smoothgrad_sq,
        vargrad,
    )
    visualizer = visualizer.value(eval_record, epochs)
    assert visualizer.get_plt("Gradient", absolute) is not None
    assert sum([len(i.images) for i in visualizer.fig.axes]) == n_class
    assert len([axis for axis in visualizer.fig.axes if axis.get_title()]) == n_class
    plt.close(visualizer.fig)


@pytest.mark.parametrize(
    "epochs, n_class",
    [
        (Epochs(get_preprocessed_data_list(2)), 2),
        (Epochs(get_preprocessed_data_list(3)), 3),
        (Epochs(get_preprocessed_data_list(4)), 4),
    ],
)
@pytest.mark.parametrize("mask_out", [True, False])
@pytest.mark.parametrize("visualizer", get_remaining_visualizer())
def test_eval_plot(epochs, n_class, mask_out, visualizer):
    label = np.ones(10)
    output = np.ones((10, n_class))
    gradient = {i: np.zeros((10, 2, 100)) for i in range(n_class)}
    if mask_out:
        gradient[0] = np.array([])
    epochs.set_channels(ch_names, np.random.rand(len(ch_names), 3))

    # Create dummy data for new EvalRecord arguments
    gradient_input = gradient.copy()
    smoothgrad = gradient.copy()
    smoothgrad_sq = gradient.copy()
    vargrad = gradient.copy()

    if mask_out:
        with pytest.raises(SaliencyArtifactIntegrityError) as error:
            _bound_eval_record(
                epochs,
                label,
                output,
                gradient,
                gradient_input,
                smoothgrad,
                smoothgrad_sq,
                vargrad,
            )
        assert error.value.reason is SaliencyIntegrityReason.PARTIAL_COVERAGE
        return
    eval_record = _bound_eval_record(
        epochs,
        label,
        output,
        gradient,
        gradient_input,
        smoothgrad,
        smoothgrad_sq,
        vargrad,
    )
    visualizer = visualizer.value(eval_record, epochs)
    assert visualizer.get_plt("Gradient") is not None
    assert sum([len(i.images) for i in visualizer.fig.axes]) == n_class
    assert len([axis for axis in visualizer.fig.axes if axis.get_title()]) == n_class
    plt.close(visualizer.fig)


@pytest.mark.parametrize("visualizer", list(VisualizerType))
def test_saliency_visualizers_use_available_label_keys(visualizer):
    """Saliency plots should not assume class keys start at zero."""
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {1: "left", 2: "right"}
    epochs.event_id = {"left": 1, "right": 2}
    epochs.set_channels(ch_names, np.random.rand(len(ch_names), 3).tolist())

    label = np.array([1, 2, 1, 2])
    output = np.ones((4, 2))
    gradient = {
        0: np.ones((2, len(ch_names), 100)),
        1: np.ones((2, len(ch_names), 100)) * 2,
    }
    eval_record = _bound_eval_record(
        epochs,
        label,
        output,
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    saliency_viz = visualizer.value(eval_record, epochs)
    if visualizer in get_abs_visualizer():
        fig = saliency_viz.get_plt("Gradient", False)
    else:
        fig = saliency_viz.get_plt("Gradient")

    assert fig is not None
    titles = [axis.get_title() for axis in saliency_viz.fig.axes if axis.get_title()]
    assert set(titles) == {"left", "right"}
    plt.close(saliency_viz.fig)


def test_saliency_spectrogram_places_low_frequencies_at_the_bottom():
    """Frequency plots must follow the conventional low-to-high y-axis."""
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}

    label = np.array([0, 1, 0, 1])
    output = np.ones((4, 2))
    gradient = {
        0: np.ones((2, len(ch_names), 100)),
        1: np.ones((2, len(ch_names), 100)) * 2,
    }
    eval_record = _bound_eval_record(
        epochs,
        label,
        output,
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient")
    plot_axes = [axis for axis in fig.axes if axis.get_title()]

    assert plot_axes
    for axis in plot_axes:
        image = axis.images[0]
        assert image.origin == "lower"
        assert axis.get_ylim()[0] < axis.get_ylim()[1]

    plt.close(fig)


def test_saliency_map_uses_real_epoch_time_bounds_and_compact_ticks():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    epochs.sfreq = 128.0
    epochs.tmin = -0.5
    sample_count = 193
    gradient = {
        0: np.ones((2, len(ch_names), sample_count)),
        1: np.ones((2, len(ch_names), sample_count)) * 2,
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencyMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient", False)
    plot_axes = [axis for axis in fig.axes if axis.images]

    assert plot_axes
    expected_end = -0.5 + (sample_count - 1) / 128.0
    for axis in plot_axes:
        labels = [float(label.get_text()) for label in axis.get_xticklabels()]
        assert len(labels) == 4
        assert labels[0] == pytest.approx(-0.5)
        assert labels[-1] == pytest.approx(expected_end)

    plt.close(fig)


def test_saliency_spectrogram_uses_stft_bin_support_without_boundary_padding():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    epochs.sfreq = 128.0
    epochs.tmin = -0.5
    sample_count = 193
    gradient = {
        0: np.ones((2, len(ch_names), sample_count)),
        1: np.ones((2, len(ch_names), sample_count)) * 2,
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient")
    plot_axes = [axis for axis in fig.axes if axis.get_title()]

    assert plot_axes
    for axis in plot_axes:
        x_min, x_max, y_min, y_max = axis.images[0].get_extent()
        assert x_min == pytest.approx(-0.25)
        assert x_max == pytest.approx(0.75)
        assert y_min == pytest.approx(0.0)
        assert y_max == pytest.approx(64.0)
    assert fig._suptitle is not None
    assert "attribution magnitude" in fig._suptitle.get_text().lower()

    plt.close(fig)


def test_saliency_spectrogram_positions_bins_at_scipy_stft_time_centers():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    epochs.sfreq = 128.0
    epochs.tmin = -0.5
    sample_count = 193
    raw_saliency = np.zeros((2, len(ch_names), sample_count))
    raw_saliency[:, :, 64] = 1.0
    gradient = {0: raw_saliency}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )
    segment_samples = 128
    overlap_samples = 64
    _, stft_centers, _ = signal.stft(
        raw_saliency,
        fs=epochs.sfreq,
        axis=-1,
        nperseg=segment_samples,
        noverlap=overlap_samples,
        boundary=None,
        padded=False,
    )
    expected_centers = epochs.tmin + stft_centers

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient")
    image = fig.axes[0].images[0]
    rendered = np.asarray(image.get_array())
    x_min, x_max, _, _ = image.get_extent()
    pixel_width = (x_max - x_min) / rendered.shape[1]
    rendered_centers = x_min + pixel_width * (np.arange(rendered.shape[1]) + 0.5)

    np.testing.assert_allclose(expected_centers, [0.0, 0.5])
    np.testing.assert_allclose(rendered_centers, expected_centers)
    peak_time_index = int(np.argmax(np.sum(rendered, axis=0)))
    assert rendered_centers[peak_time_index] == pytest.approx(0.0)
    assert image.get_interpolation() == "nearest"
    plt.close(fig)


def test_saliency_spectrogram_handles_epoch_shorter_than_one_second():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    epochs.sfreq = 128.0
    sample_count = 32
    gradient = {0: np.ones((2, len(ch_names), sample_count))}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient")

    assert fig is not None
    image = fig.axes[0].images[0]
    assert np.asarray(image.get_array()).shape[1] == 1
    x_min, x_max, y_min, y_max = image.get_extent()
    assert (x_min + x_max) / 2 == pytest.approx(0.125)
    assert x_min == pytest.approx(0.0)
    assert x_max == pytest.approx(sample_count / 128.0)
    assert y_min < y_max
    plt.close(fig)


def test_topomap_preserves_constant_saliency_and_marks_sparse_interpolation():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    sparse_channels = ["C3", "C4", "Cz", "Pz"]
    montage = mne.channels.make_standard_montage("standard_1020")
    montage_positions = montage.get_positions()["ch_pos"]
    positions = [montage_positions[name] for name in sparse_channels]
    epochs.ch_names = sparse_channels
    epochs.channel_position = positions
    gradient = {0: np.zeros((2, len(sparse_channels), 64))}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )
    captured_data: list[np.ndarray] = []

    def capture_topomap(*, data, **kwargs):
        captured_data.append(np.asarray(data).copy())
        axes = kwargs["axes"]
        image = axes.imshow(np.zeros((2, 2)))
        return image, None

    visualizer = VisualizerType.SaliencyTopoMap.value(eval_record, epochs)
    with patch("mne.viz.plot_topomap", side_effect=capture_topomap):
        fig = visualizer.get_plt("Gradient", False)

    assert captured_data
    np.testing.assert_array_equal(captured_data[0], np.zeros(len(sparse_channels)))
    figure_notes = [text.get_text() for text in fig.texts]
    assert any("Sparse 4-channel interpolation" in text for text in figure_notes)
    plt.close(fig)


def test_topomap_rejects_channel_position_count_mismatch():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    epochs.ch_names = ["C3", "C4", "Cz", "Pz"]
    epochs.channel_position = np.zeros((4, 3)).tolist()
    gradient = {0: np.zeros((2, 4, 64))}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )
    epochs.channel_position = np.zeros((3, 3)).tolist()

    visualizer = VisualizerType.SaliencyTopoMap.value(eval_record, epochs)

    with pytest.raises(ValueError, match=r"channel names.*montage positions"):
        visualizer.get_plt("Gradient", False)


def test_saliency_map_uses_sequential_scale_for_nonnegative_methods():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    gradient = {0: np.full((2, len(ch_names), 64), 2.0)}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencyMap.value(eval_record, epochs)
    fig = visualizer.get_plt("SmoothGrad_Squared", False)
    image = fig.axes[0].images[0]

    assert image.get_cmap().name == "Reds"
    assert image.get_clim() == pytest.approx((0.0, 2.0))
    plt.close(fig)


def test_saliency_map_centers_signed_scale_on_zero():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left"}
    epochs.event_id = {"left": 0}
    signed = np.empty((2, len(ch_names), 64))
    signed[:, 0, :] = -2.0
    signed[:, 1, :] = 1.0
    gradient = {0: signed}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 0]),
        np.ones((2, 1)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencyMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient", False)
    image = fig.axes[0].images[0]

    assert image.get_cmap().name == "coolwarm"
    assert image.get_clim() == pytest.approx((-2.0, 2.0))
    plt.close(fig)


def test_saliency_map_shares_signed_scale_across_classes():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    left = np.full((2, len(ch_names), 64), -1.0)
    right = np.full((2, len(ch_names), 64), 4.0)
    gradient = {0: left, 1: right}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencyMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient", False)
    images = [axis.images[0] for axis in fig.axes if axis.images]

    assert len(images) == 2
    for image in images:
        assert image.get_clim() == pytest.approx((-4.0, 4.0))
    plt.close(fig)


@pytest.mark.parametrize(
    ("method", "absolute"),
    [("SmoothGrad_Squared", False), ("Gradient", True)],
)
def test_saliency_map_shares_nonnegative_scale_across_classes(method, absolute):
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    gradient = {
        0: np.full((2, len(ch_names), 64), 2.0),
        1: np.full((2, len(ch_names), 64), 7.0),
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencyMap.value(eval_record, epochs)
    fig = visualizer.get_plt(method, absolute)
    images = [axis.images[0] for axis in fig.axes if axis.images]

    assert len(images) == 2
    for image in images:
        assert image.get_clim() == pytest.approx((0.0, 7.0))
    plt.close(fig)


@pytest.mark.parametrize(
    ("method", "absolute", "class_values", "expected_limits"),
    [
        (
            "Gradient",
            False,
            ([-1.0, 1.0, -0.5, 0.5], [-4.0, 2.0, -3.0, 1.0]),
            (-4.0, 4.0),
        ),
        (
            "SmoothGrad_Squared",
            False,
            ([1.0, 2.0, 1.5, 0.5], [7.0, 3.0, 4.0, 2.0]),
            (0.0, 7.0),
        ),
        (
            "Gradient",
            True,
            ([-1.0, -2.0, 1.5, 0.5], [-7.0, 3.0, 4.0, 2.0]),
            (0.0, 7.0),
        ),
    ],
)
def test_topomap_shares_scale_across_classes(
    method,
    absolute,
    class_values,
    expected_limits,
):
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    channels = ["C3", "C4", "Cz", "Pz"]
    montage = mne.channels.make_standard_montage("standard_1020")
    montage_positions = montage.get_positions()["ch_pos"]
    epochs.ch_names = channels
    epochs.channel_position = [montage_positions[name] for name in channels]
    gradient = {
        class_index: np.broadcast_to(
            np.asarray(values)[None, :, None],
            (2, len(channels), 64),
        ).copy()
        for class_index, values in enumerate(class_values)
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )
    captured_limits: list[tuple[float, float]] = []

    def capture_topomap(*, data, **kwargs):
        del data
        captured_limits.append(kwargs["vlim"])
        axes = kwargs["axes"]
        image = axes.imshow(
            np.zeros((2, 2)),
            vmin=kwargs["vlim"][0],
            vmax=kwargs["vlim"][1],
        )
        return image, None

    visualizer = VisualizerType.SaliencyTopoMap.value(eval_record, epochs)
    with patch("mne.viz.plot_topomap", side_effect=capture_topomap):
        fig = visualizer.get_plt(method, absolute)

    assert len(captured_limits) == 2
    for limits in captured_limits:
        assert limits == pytest.approx(expected_limits)
    plt.close(fig)


def test_saliency_spectrogram_shares_robust_scale_across_classes():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    epochs.sfreq = 128.0
    sample_count = 193
    time = np.arange(sample_count) / epochs.sfreq
    base_signal = np.sin(2 * np.pi * 10 * time)
    gradient = {
        0: np.broadcast_to(
            base_signal[None, None, :],
            (2, len(ch_names), sample_count),
        )
        .copy()
        .astype(np.float32),
        1: np.broadcast_to(
            (5 * base_signal)[None, None, :],
            (2, len(ch_names), sample_count),
        )
        .copy()
        .astype(np.float32),
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    observed_stft_dtypes = []
    original_stft = signal.stft

    def recording_stft(values, *args, **kwargs):
        observed_stft_dtypes.append(np.asarray(values).dtype)
        return original_stft(values, *args, **kwargs)

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    with patch(
        "XBrainLab.backend.visualization.saliency_spectrogram_map.signal.stft",
        side_effect=recording_stft,
    ):
        fig = visualizer.get_plt("Gradient")
    images = [axis.images[0] for axis in fig.axes if axis.images]
    shared_limits = images[0].get_clim()

    assert len(images) == 2
    assert len(fig.axes) == 3  # two class plots and one shared colorbar
    for image in images:
        assert image.get_clim() == pytest.approx(shared_limits)
        assert image.get_cmap().name == "cividis"
    assert shared_limits[0] == 0.0
    assert shared_limits[1] > 0.0
    assert observed_stft_dtypes == [np.dtype(np.float32), np.dtype(np.float32)]
    assert "shared p99 scale" in fig.axes[-1].get_ylabel()
    assert visualizer.spectrogram_display_scale["upper_percentile"] == 99.0
    assert visualizer.spectrogram_display_scale["data_max"] >= shared_limits[1]
    assert len(visualizer.spectrogram_diagnostics) == 2
    for diagnostic in visualizer.spectrogram_diagnostics:
        assert diagnostic["finite_count"] > 0
        assert diagnostic["nan_count"] == 0
        assert diagnostic["inf_count"] == 0
        assert len(diagnostic["frequency_bins"]) > 0
        assert all(
            "p1" in frequency_bin and "p99" in frequency_bin
            for frequency_bin in diagnostic["frequency_bins"]
        )
    plt.close(fig)


def test_saliency_spectrogram_robust_scale_is_not_owned_by_one_outlier():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    epochs.sfreq = 128.0
    sample_count = 256
    time = np.arange(sample_count) / epochs.sfreq
    base_signal = np.sin(2 * np.pi * 10 * time)
    left = np.broadcast_to(
        base_signal[None, None, :],
        (8, len(ch_names), sample_count),
    ).copy()
    right = np.broadcast_to(
        (2 * base_signal)[None, None, :],
        (8, len(ch_names), sample_count),
    ).copy()
    left[0, 0, 0] = 1e9
    gradient = {0: left, 1: right}
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1] * 8),
        np.ones((16, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    visualizer = VisualizerType.SaliencySpectrogramMap.value(eval_record, epochs)
    fig = visualizer.get_plt("Gradient")
    images = [axis.images[0] for axis in fig.axes if axis.images]
    display_max = images[0].get_clim()[1]
    data_max = max(float(np.nanmax(image.get_array())) for image in images)

    assert len(images) == 2
    assert display_max < data_max
    assert all(image.norm is images[0].norm for image in images)
    assert images[0].norm.clip is False
    assert visualizer.spectrogram_display_scale["over_range_count"] > 0
    assert visualizer.spectrogram_display_scale["over_range_ratio"] > 0
    assert visualizer.spectrogram_display_scale["data_max"] == pytest.approx(data_max)
    assert "shared p99 scale" in fig.axes[-1].get_ylabel()
    plt.close(fig)


@pytest.mark.parametrize(
    "visualizer_type",
    [VisualizerType.SaliencyMap, VisualizerType.SaliencyTopoMap],
)
def test_saliency_class_panels_share_one_colorbar(visualizer_type):
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    channels = ["C3", "C4", "Cz", "Pz"]
    montage = mne.channels.make_standard_montage("standard_1020")
    montage_positions = montage.get_positions()["ch_pos"]
    epochs.ch_names = channels
    epochs.channel_position = [montage_positions[name] for name in channels]
    gradient = {
        0: np.ones((2, len(channels), 64)),
        1: np.ones((2, len(channels), 64)) * 2,
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    fig = visualizer_type.value(eval_record, epochs).get_plt("Gradient", False)
    titled_axes = [axis for axis in fig.axes if axis.get_title()]

    assert len(titled_axes) == 2
    assert len(fig.axes) == 3  # two class plots and one shared colorbar
    assert titled_axes[0].get_position().x1 < titled_axes[1].get_position().x0
    plt.close(fig)


def test_topomap_colorbar_tight_bounds_leave_readable_right_margin():
    epochs = Epochs(get_preprocessed_data_list(2))
    epochs.label_map = {0: "left", 1: "right"}
    epochs.event_id = {"left": 0, "right": 1}
    channels = ["C3", "C4", "Cz", "Pz"]
    montage = mne.channels.make_standard_montage("standard_1020")
    montage_positions = montage.get_positions()["ch_pos"]
    epochs.ch_names = channels
    epochs.channel_position = [montage_positions[name] for name in channels]
    class_values = (
        np.array([-8.0, -4.0, 2.0, 6.0]) * 1e-4,
        np.array([-6.0, -2.0, 4.0, 8.0]) * 1e-4,
    )
    gradient = {
        class_index: np.broadcast_to(
            values[None, :, None],
            (2, len(channels), 64),
        ).copy()
        for class_index, values in enumerate(class_values)
    }
    eval_record = _bound_eval_record(
        epochs,
        np.array([0, 1, 0, 1]),
        np.ones((4, 2)),
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )

    fig = VisualizerType.SaliencyTopoMap.value(eval_record, epochs).get_plt(
        "Gradient",
        False,
    )
    # Match the compact canvas used by the docked Visualization panel.
    fig.set_size_inches(4.74, 4.54, forward=True)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    renderer = canvas.get_renderer()
    canvas_width, _canvas_height = canvas.get_width_height()
    colorbar_axis = fig.axes[-1]
    colorbar_bounds = colorbar_axis.get_tightbbox(renderer)

    assert colorbar_bounds is not None
    assert colorbar_bounds.x1 <= canvas_width - 6
    assert colorbar_axis.yaxis.get_offset_text().get_text()
    plt.close(fig)
