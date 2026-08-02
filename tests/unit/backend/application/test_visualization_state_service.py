"""Focused contract tests for the manager-owned Visualization product port."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace
from typing import Any

from XBrainLab.backend.application import ApplicationService, VisualizeCommand
from XBrainLab.backend.services.visualization_state_service import (
    VisualizationStateService,
)
from XBrainLab.backend.study import Study


class _TrainingManager:
    def __init__(self) -> None:
        self.holders = (object(), object())
        self.params: dict[str, Any] | None = None
        self.schedule: Any = None

    def get_training_plan_holders_snapshot(self) -> tuple[Any, ...]:
        return self.holders

    def set_saliency_params(self, params: dict[str, Any]) -> Any:
        self.params = params
        return self.schedule

    def get_saliency_params(self) -> dict[str, Any] | None:
        return self.params


def test_visualization_state_service_delegates_only_to_training_manager() -> None:
    manager = _TrainingManager()
    service = VisualizationStateService(manager)
    params = {"method": "Gradient"}

    schedule = service.set_saliency_params(params)

    assert schedule is None
    assert service.get_trainers() == list(manager.holders)
    assert service.get_saliency_params() is params


def test_visualization_state_service_preserves_schedule_notification_policy() -> None:
    manager = _TrainingManager()
    service = VisualizationStateService(manager)
    notifications: list[str] = []
    service.subscribe("saliency_changed", lambda: notifications.append("changed"))

    manager.schedule = SimpleNamespace(scheduled=False)
    rejected = service.set_saliency_params({"method": "Gradient"})
    manager.schedule = SimpleNamespace(scheduled=True)
    scheduled = service.set_saliency_params({"method": "SmoothGrad"})

    assert rejected is not None and rejected.scheduled is False
    assert scheduled is not None and scheduled.scheduled is True
    assert notifications == ["changed"]


def test_visualization_state_service_preserves_batched_delivery_readback() -> None:
    manager = _TrainingManager()
    service = VisualizationStateService(manager)
    attempts = 0

    def reject_delivery() -> bool:
        nonlocal attempts
        attempts += 1
        return False

    service.subscribe("saliency_changed", reject_delivery)
    batch: AbstractContextManager[None] = service.batch_notifications()
    with batch:
        generation = service.notification_batch_generation
        assert generation is not None
        assert service.is_notification_batch_active(generation) is True
        service.set_saliency_params({"method": "Gradient"})

    assert attempts == 1
    assert service.is_notification_batch_active(generation) is False
    assert service.consume_batched_delivery("saliency_changed", generation) is False
    assert service.consume_batched_delivery("saliency_changed", generation) is None


def test_application_visualization_composition_never_resolves_controller(
    monkeypatch,
) -> None:
    study = Study()
    original_get_controller = study.get_controller
    resolved_names: list[str] = []

    def reject_visualization_controller(name: str) -> Any:
        resolved_names.append(name)
        if name == "visualization":
            raise AssertionError("Application composition resolved a UI controller")
        return original_get_controller(name)

    monkeypatch.setattr(study, "get_controller", reject_visualization_controller)

    service = ApplicationService(study)
    result = service.execute(VisualizeCommand())

    assert result.failed is True
    assert service.visualization is study.visualization_state_service
    assert "visualization" not in resolved_names
