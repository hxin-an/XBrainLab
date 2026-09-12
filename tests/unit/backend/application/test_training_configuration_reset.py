"""Focused tests for the lightweight training-configuration reset owner."""

from __future__ import annotations

import pytest

from XBrainLab.backend.application.training_configuration_reset import (
    TrainingConfigurationResetService,
)
from XBrainLab.backend.application.training_recommendation import (
    TrainingRecommendationContext,
    TrainingRecommendationService,
)


class _TrainingNotifier:
    def __init__(self, runtime: _TrainingRuntime, *, fail: bool) -> None:
        self.runtime = runtime
        self.fail = fail
        self.notifications: list[tuple[str, object, object, object]] = []

    def notify(self, event_name: str) -> None:
        self.notifications.append(
            (
                event_name,
                self.runtime.model_holder,
                self.runtime.training_option,
                self.runtime.saliency_params,
            )
        )
        if self.fail:
            raise RuntimeError("Injected observer failure")


class _TrainingRuntime:
    def __init__(self) -> None:
        self.model_holder = object()
        self.training_option = object()
        self.saliency_params = {"SmoothGrad": {"nt_samples": 5}}
        self.clear_count = 0

    def clear_configuration(self) -> None:
        self.model_holder = None
        self.training_option = None
        self.saliency_params = None
        self.clear_count += 1


@pytest.mark.parametrize("notification_fails", [False, True])
def test_configuration_reset_publishes_cleared_runtime_and_clears_recommendation(
    notification_fails: bool,
) -> None:
    runtime = _TrainingRuntime()
    training = _TrainingNotifier(runtime, fail=notification_fails)
    recommendation = TrainingRecommendationService()
    context = TrainingRecommendationContext(
        model_name="braindecode.eegnet",
        model_params={},
        epoch_count=64,
        n_channels=4,
        n_times=128,
        dataset_count=1,
        training_sample_count=40,
        validation_sample_count=12,
        device="cpu",
    )
    before = recommendation.recommend(context)
    assert recommendation.for_state_snapshot(context, current_option=None) is before
    service = TrainingConfigurationResetService(
        training=training,
        training_runtime=runtime,  # type: ignore[arg-type]
        recommendation=recommendation,
    )

    service.clear()

    assert runtime.model_holder is None
    assert runtime.training_option is None
    assert runtime.saliency_params is None
    assert runtime.clear_count == 1
    assert training.notifications == [("config_changed", None, None, None)]
    assert recommendation.for_state_snapshot(context, current_option=None) is None
