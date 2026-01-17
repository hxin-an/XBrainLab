import numpy as np
import pytest

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
    visualizer = Visualizer(eval_record, None)
    with pytest.raises(NotImplementedError):
        visualizer.get_plt()

    assert np.array_equal(
        visualizer.get_saliency("Gradient", 0), np.zeros((10, 2, 3, 4))
    )
    assert np.array_equal(
        visualizer.get_saliency("Gradient", 1), np.ones((10, 2, 3, 4))
    )
