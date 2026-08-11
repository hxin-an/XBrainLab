"""Scientific aggregation regressions shared by saliency visualizations."""

import numpy as np

from XBrainLab.backend.visualization.saliency_semantics import (
    mean_saliency_over_trials,
)


def test_trial_mean_preserves_cancellation_sensitive_signed_signal() -> None:
    values = np.array([1e8, 1.0, -1e8], dtype=np.float32).reshape(3, 1, 1)

    result = mean_saliency_over_trials(values, absolute=False)

    assert result.dtype == np.float64
    np.testing.assert_allclose(result, np.array([[1.0 / 3.0]]), rtol=0, atol=1e-12)


def test_trial_mean_preserves_absolute_saliency_semantics() -> None:
    values = np.array([-2.0, 1.0, 4.0], dtype=np.float32).reshape(3, 1, 1)

    result = mean_saliency_over_trials(values, absolute=True)

    assert result.dtype == np.float64
    np.testing.assert_allclose(result, np.array([[7.0 / 3.0]]), rtol=0, atol=1e-12)
