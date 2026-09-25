from dataclasses import replace

import numpy as np
import pytest
from matplotlib import pyplot as plt

from XBrainLab.backend.application.saliency_render import SaliencyRenderData
from XBrainLab.backend.visualization.base import (
    Visualizer,
    resolve_saliency_class_identities,
)


def _render_data(*, keys=(0, 1), classes=((0, "left"), (1, "right"))):
    return SaliencyRenderData(
        method="Gradient",
        saliency_by_class={
            key: np.full((2, 2, 4), index, dtype=float)
            for index, key in enumerate(keys)
        },
        class_map=classes,
        event_ids={str(name): int(code) for code, name in classes},
        channel_names=("C3", "C4"),
        channel_positions=(),
        sfreq=100.0,
        tmin=-0.2,
    )


def test_visualizer():
    visualizer = Visualizer(_render_data())
    with pytest.raises(NotImplementedError):
        visualizer.get_plt()

    labels = visualizer.iter_saliency_by_label("Gradient")
    assert [(key, name) for key, name, _ in labels] == [(0, "left"), (1, "right")]
    np.testing.assert_array_equal(labels[0][2], np.zeros((2, 2, 4)))
    np.testing.assert_array_equal(labels[1][2], np.ones((2, 2, 4)))


def test_visualizer_closes_owned_figure_when_plotting_fails():
    class FailingVisualizer(Visualizer):
        def _get_plt(self, *args, **kwargs):
            raise RuntimeError("boom")

    initial_figures = plt.get_fignums()
    visualizer = FailingVisualizer(_render_data())
    with pytest.raises(RuntimeError, match="boom"):
        visualizer.get_plt()
    assert visualizer.fig is None
    assert plt.get_fignums() == initial_figures


@pytest.mark.parametrize(
    ("keys", "classes", "expected"),
    [
        (
            (0, 1),
            ((769, "Left hand"), (770, "Right hand")),
            [(0, "Left hand"), (1, "Right hand")],
        ),
        ((0, 1), ((1, "left"), (2, "right")), [(0, "left"), (1, "right")]),
        (("0", "1"), ((0, "left"), (1, "right")), [("0", "left"), ("1", "right")]),
        ((769, 770), ((769, "left"), (770, "right")), [(769, "left"), (770, "right")]),
    ],
)
def test_visualizer_keeps_class_identity_and_values(keys, classes, expected):
    visualizer = Visualizer(_render_data(keys=keys, classes=classes))
    labels = visualizer.iter_saliency_by_label("Gradient")
    assert [(key, name) for key, name, _ in labels] == expected
    np.testing.assert_array_equal(labels[1][2], np.ones((2, 2, 4)))


def test_class_resolver_does_not_assign_extra_event_labels_to_model_classes():
    identities = resolve_saliency_class_identities(
        {0: np.ones((1, 2, 4)), 1: np.ones((1, 2, 4))},
        [(768, "Trial timing"), (769, "Left hand"), (770, "Right hand")],
        expected_class_count=2,
    )
    assert [(item.saliency_key, item.display_name) for item in identities] == [
        (0, "0"),
        (1, "1"),
    ]


def test_iter_saliency_by_label_rejects_empty_class_arrays():
    data = replace(
        _render_data(),
        saliency_by_class={0: np.empty((0, 2, 4)), 1: np.ones((1, 2, 4))},
    )
    with pytest.raises(ValueError, match=r"missing.*left"):
        Visualizer(data).iter_saliency_by_label("Gradient")


def test_iter_saliency_by_label_rejects_incomplete_class_coverage():
    data = replace(_render_data(), saliency_by_class={0: np.ones((1, 2, 4))})
    with pytest.raises(ValueError, match=r"expected 2 classes.*found 1"):
        Visualizer(data).iter_saliency_by_label("Gradient")


def test_visualizer_rejects_method_not_in_publication():
    with pytest.raises(ValueError, match="contains Gradient, not VarGrad"):
        Visualizer(_render_data()).iter_saliency_by_label("VarGrad")
