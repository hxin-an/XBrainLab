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
