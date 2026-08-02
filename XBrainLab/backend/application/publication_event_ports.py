"""Application-owned ports for asynchronous publication lifecycle events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from XBrainLab.backend.training_state_contract import TrainingLifecycleEvent

TrainingLifecycleCallback = Callable[..., object]


class TrainingLifecycleEventPort(Protocol):
    """Training event surface required by application publication orchestration."""

    def subscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def unsubscribe_training_started(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def subscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def unsubscribe_training_updated(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def subscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def unsubscribe_training_stopped(
        self,
        callback: TrainingLifecycleCallback,
    ) -> None: ...

    def publish_training_terminal(self, event: TrainingLifecycleEvent) -> object: ...

    def publish_training_analysis(self, event: TrainingLifecycleEvent) -> object: ...


class VisualizationPublicationEventPort(Protocol):
    """Visualization event surface required by terminal saliency publication."""

    @property
    def notifications_deferred(self) -> bool: ...

    @property
    def notification_batch_generation(self) -> int | None: ...

    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None: ...

    def is_notification_batch_active(self, generation: int) -> bool: ...

    def publish_saliency_changed(self) -> object: ...


__all__ = [
    "TrainingLifecycleCallback",
    "TrainingLifecycleEventPort",
    "VisualizationPublicationEventPort",
]
