"""Focused tests for the lightweight training-configuration reset owner."""

from __future__ import annotations

from XBrainLab.backend.application.training_configuration_reset import (
    TrainingConfigurationResetService,
)


class _TrainingNotifier:
    def __init__(self) -> None:
        self.notifications: list[str] = []

    def notify(self, event_name: str) -> None:
        self.notifications.append(event_name)


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


def test_training_configuration_reset_clears_all_owned_fields_once() -> None:
    training = _TrainingNotifier()
    runtime = _TrainingRuntime()
    service = TrainingConfigurationResetService(
        training=training,
        training_runtime=runtime,  # type: ignore[arg-type]
    )

    service.clear()

    assert runtime.model_holder is None
    assert runtime.training_option is None
    assert runtime.saliency_params is None
    assert runtime.clear_count == 1
    assert training.notifications == ["config_changed"]


def test_training_configuration_reset_publishes_after_runtime_clear() -> None:
    training = _TrainingNotifier()
    runtime = _TrainingRuntime()
    service = TrainingConfigurationResetService(
        training=training,
        training_runtime=runtime,  # type: ignore[arg-type]
    )

    service.clear()

    assert runtime.clear_count == 1
    assert training.notifications == ["config_changed"]
