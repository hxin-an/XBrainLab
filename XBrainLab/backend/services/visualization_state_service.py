"""Manager-owned Visualization operations shared by product command services."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from XBrainLab.backend.utils.observer import Observable


class VisualizationManagerPort(Protocol):
    """Training-manager state required by Visualization product commands."""

    def get_training_plan_holders_snapshot(self) -> tuple[Any, ...]: ...
    def set_saliency_params(self, saliency_params: dict[str, Any]) -> Any: ...
    def get_saliency_params(self) -> dict[str, Any] | None: ...


class VisualizationProductPort(Protocol):
    """Visualization command and publication surface used by the application."""

    @property
    def notifications_deferred(self) -> bool: ...

    @property
    def notification_batch_generation(self) -> int | None: ...

    def get_trainers(self) -> list[Any]: ...
    def set_saliency_params(self, params: dict[str, Any]) -> Any: ...
    def get_saliency_params(self) -> dict[str, Any] | None: ...
    def subscribe(self, event_name: str, callback: Any) -> None: ...
    def notify(self, event_name: str, *args: Any, **kwargs: Any) -> bool: ...
    def batch_notifications(self) -> AbstractContextManager[None]: ...
    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None: ...
    def is_notification_batch_active(self, generation: int) -> bool: ...
    def publish_saliency_changed(self) -> bool: ...


class VisualizationStateService(Observable):
    """Own Visualization product operations without resolving a UI controller."""

    def __init__(self, training_manager: VisualizationManagerPort) -> None:
        super().__init__()
        self._training_manager = training_manager

    def get_trainers(self) -> list[Any]:
        """Return one stable manager snapshot in the controller-compatible shape."""
        return list(self._training_manager.get_training_plan_holders_snapshot())

    def set_saliency_params(self, params: dict[str, Any]) -> Any:
        """Apply saliency parameters and preserve accepted-change notification."""
        schedule = self._training_manager.set_saliency_params(params)
        if schedule is None or schedule.scheduled:
            self.publish_saliency_changed()
        return schedule

    def get_saliency_params(self) -> dict[str, Any] | None:
        """Read back authoritative manager parameters for command verification."""
        return self._training_manager.get_saliency_params()

    def publish_saliency_changed(self) -> bool:
        """Publish the semantic event consumed by application lifecycle ports."""
        return self.notify("saliency_changed")


__all__ = [
    "VisualizationManagerPort",
    "VisualizationProductPort",
    "VisualizationStateService",
]
