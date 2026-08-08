from __future__ import annotations

import numpy as np
import pytest

from XBrainLab.backend.visualization.saliency_semantics import (
    SALIENCY_RED_BLUE_CMAP,
    saliency_color_scale,
)
from XBrainLab.backend.visualization.saliency_spectrogram_map import (
    SaliencySpectrogramMapViz,
)


def test_normalized_signed_and_nonnegative_views_use_fixed_shared_limits() -> None:
    signed = saliency_color_scale(
        "Gradient",
        [np.array([-0.2, 0.7])],
        absolute=False,
        normalized=True,
    )
    nonnegative = saliency_color_scale(
        "Gradient",
        [np.array([0.2, 0.7])],
        absolute=True,
        normalized=True,
    )

    assert signed == (SALIENCY_RED_BLUE_CMAP, -1.0, 1.0)
    assert nonnegative == ("Reds", 0.0, 1.0)


def test_normalized_spectrogram_uses_one_zero_to_one_scale() -> None:
    norm, label, details = SaliencySpectrogramMapViz._build_shared_display_scale(
        [np.array([[0.05, 0.8]]), np.array([[0.2, 1.0]])],
        normalized=True,
    )

    assert norm.vmin == pytest.approx(0.0)
    assert norm.vmax == pytest.approx(1.0)
    assert label == "Normalized attribution magnitude"
    assert details["scale"] == "normalized"
