import mne
import numpy as np
import pytest
from matplotlib import pyplot as plt

from XBrainLab.backend.dataset import Epochs
from XBrainLab.backend.load_data import Raw
from XBrainLab.backend.training.record import EvalRecord
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
    output = np.ones((10, 2))
    gradient = {i: np.zeros((10, 2, 4)) for i in range(n_class)}
    if mask_out:
        gradient[0] = np.array([])
        n_class -= 1
    epochs.set_channels(ch_names, np.random.rand(len(ch_names), 3))

    # Create dummy data for new EvalRecord arguments
    gradient_input = gradient.copy()
    smoothgrad = gradient.copy()
    smoothgrad_sq = gradient.copy()
    vargrad = gradient.copy()

    eval_record = EvalRecord(
        label, output, gradient, gradient_input, smoothgrad, smoothgrad_sq, vargrad
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
    output = np.ones((10, 2))
    gradient = {i: np.zeros((10, 2, 100)) for i in range(n_class)}
    if mask_out:
        gradient[0] = np.array([])
        n_class -= 1
    epochs.set_channels(ch_names, np.random.rand(len(ch_names), 3))

    # Create dummy data for new EvalRecord arguments
    gradient_input = gradient.copy()
    smoothgrad = gradient.copy()
    smoothgrad_sq = gradient.copy()
    vargrad = gradient.copy()

    eval_record = EvalRecord(
        label, output, gradient, gradient_input, smoothgrad, smoothgrad_sq, vargrad
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
    output = np.ones((4, 3))
    gradient = {
        1: np.ones((2, len(ch_names), 100)),
        2: np.ones((2, len(ch_names), 100)) * 2,
    }
    eval_record = EvalRecord(
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
    assert any("left" in title for title in titles)
    assert any("right" in title for title in titles)
    plt.close(saliency_viz.fig)
