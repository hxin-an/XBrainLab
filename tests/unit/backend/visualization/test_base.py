from typing import Any, cast

import numpy as np
import pytest
from matplotlib import pyplot as plt

from XBrainLab.backend.training.record import EvalRecord
from XBrainLab.backend.visualization.base import Visualizer


def test_visualizer():
    label = np.ones(10)
    output = np.ones((10, 2))
    gradient = {
        0: np.zeros((10, 2, 3, 4)),
        1: np.ones((10, 2, 3, 4)),
    }
    gradient_input = gradient.copy()
    smoothgrad = gradient.copy()
    smoothgrad_sq = gradient.copy()
    vargrad = gradient.copy()
    eval_record = EvalRecord(
        label, output, gradient, gradient_input, smoothgrad, smoothgrad_sq, vargrad
    )
    visualizer = Visualizer(eval_record, cast(Any, None))
    with pytest.raises(NotImplementedError):
        visualizer.get_plt()

    assert np.array_equal(
        visualizer.get_saliency("Gradient", 0), np.zeros((10, 2, 3, 4))
    )
    assert np.array_equal(
        visualizer.get_saliency("Gradient", 1), np.ones((10, 2, 3, 4))
    )


def test_visualizer_closes_owned_figure_when_plotting_fails():
    """Failed temporary visualizers must not leak pyplot figures."""

    class FailingVisualizer(Visualizer):
        def _get_plt(self, *args, **kwargs):
            raise RuntimeError("boom")

    plt.close("all")
    eval_record = EvalRecord(
        np.array([0]),
        np.array([[1.0]]),
        {0: np.zeros((1, 1, 1))},
        {},
        {},
        {},
        {},
    )
    visualizer = FailingVisualizer(eval_record, cast(Any, None))

    with pytest.raises(RuntimeError, match="boom"):
        visualizer.get_plt()

    assert visualizer.fig is None
    assert plt.get_fignums() == []


def test_iter_saliency_by_label_uses_label_order_when_class_keys_are_zero_based():
    """Display names should follow epoch labels when class-counts line up."""
    eval_record = EvalRecord(
        np.array([0, 1]),
        np.array([[0.8, 0.2], [0.2, 0.8]]),
        {
            0: np.ones((1, 2, 3, 4)),
            1: np.ones((1, 2, 3, 4)) * 2,
        },
        {},
        {},
        {},
        {},
    )
    epoch_data = cast(Any, type("EpochData", (), {})())
    epoch_data.label_map = {769: "Left hand", 770: "Right hand"}
    visualizer = Visualizer(eval_record, epoch_data)

    labels = visualizer.iter_saliency_by_label("Gradient")

    assert [(key, name) for key, name, _saliency in labels] == [
        (0, "Left hand"),
        (1, "Right hand"),
    ]


def test_iter_saliency_by_label_prefers_actual_saliency_keys_over_extra_labels():
    """Non-class EEG events in label_map must not hide computed saliency data."""
    eval_record = EvalRecord(
        np.array([0, 1]),
        np.array([[0.8, 0.2], [0.2, 0.8]]),
        {
            0: np.ones((1, 2, 3, 4)),
            1: np.ones((1, 2, 3, 4)) * 2,
        },
        {},
        {},
        {},
        {},
    )
    epoch_data = cast(Any, type("EpochData", (), {})())
    epoch_data.label_map = {
        768: "Trial timing",
        769: "Left hand",
        770: "Right hand",
    }
    visualizer = Visualizer(eval_record, epoch_data)

    labels = visualizer.iter_saliency_by_label("Gradient")

    assert [key for key, _name, _saliency in labels] == [0, 1]
    assert all(saliency.size > 0 for _key, _name, saliency in labels)


def test_iter_saliency_by_label_skips_empty_class_arrays():
    eval_record = EvalRecord(
        np.array([1]),
        np.array([[0.2, 0.8]]),
        {
            0: np.empty((0, 2, 3, 4)),
            1: np.ones((1, 2, 3, 4)),
        },
        {},
        {},
        {},
        {},
    )
    epoch_data = cast(Any, type("EpochData", (), {})())
    epoch_data.label_map = {0: "class 0", 1: "class 1"}
    visualizer = Visualizer(eval_record, epoch_data)

    labels = visualizer.iter_saliency_by_label("Gradient")

    assert [(key, name) for key, name, _saliency in labels] == [(1, "class 1")]


def test_visualizer_resolves_string_saliency_keys():
    label = np.ones(10)
    output = np.ones((10, 2))
    gradient = {
        "0": np.zeros((10, 2, 3, 4)),
        "1": np.ones((10, 2, 3, 4)),
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
    visualizer = Visualizer(eval_record, None)

    assert np.array_equal(
        visualizer.get_saliency("Gradient", 1), np.ones((10, 2, 3, 4))
    )


def test_visualizer_iterates_available_saliency_without_zero_based_assumption():
    label = np.ones(10)
    output = np.ones((10, 2))
    gradient = {
        769: np.zeros((10, 2, 3, 4)),
        770: np.ones((10, 2, 3, 4)),
    }
    epoch_data = type(
        "EpochData",
        (),
        {"label_map": {769: "left", 770: "right"}},
    )()
    eval_record = EvalRecord(
        label,
        output,
        gradient,
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
        gradient.copy(),
    )
    visualizer = Visualizer(eval_record, epoch_data)

    saliency_by_label = visualizer.iter_saliency_by_label("Gradient")

    assert [item[1] for item in saliency_by_label] == ["left", "right"]
