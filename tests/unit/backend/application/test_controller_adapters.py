from __future__ import annotations

from typing import Any, cast

from XBrainLab.backend.application.controller_adapters import (
    DatasetControllerAdapter,
    PreprocessControllerAdapter,
    VisualizationControllerAdapter,
)
from XBrainLab.backend.study import Study


class _DatasetController:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, int]] = []
        self.metadata_updates: list[tuple[int, str | None, str | None]] = []

    def get_smart_filter_suggestions(self, data: Any, target_count: int) -> list[int]:
        self.calls.append((data, target_count))
        return [1, 2]

    def update_metadata_batch(
        self,
        updates: list[tuple[int, str | None, str | None]],
    ) -> int:
        self.metadata_updates = list(updates)
        return len(updates)


class _PreprocessController:
    def __init__(self) -> None:
        self.standard_options: dict[str, Any] = {}

    def apply_standard_pipeline(self, **options: Any) -> bool:
        self.standard_options = dict(options)
        return True


class _VisualizationController:
    notifications_deferred = True
    notification_batch_generation = 7

    def consume_batched_delivery(
        self,
        event_name: str,
        generation: int,
    ) -> bool | None:
        return event_name == "saliency_changed" and generation == 7

    def is_notification_batch_active(self, generation: int) -> bool:
        return generation == 7


class _Study:
    def __init__(self) -> None:
        self.dataset = _DatasetController()
        self.preprocess = _PreprocessController()
        self.visualization = _VisualizationController()

    def get_controller(self, name: str) -> Any:
        return getattr(self, name)


def test_dataset_adapter_preserves_smart_filter_target_file_argument() -> None:
    study = _Study()
    raw = object()

    suggestions = DatasetControllerAdapter(
        cast(Study, study)
    ).get_smart_filter_suggestions(raw, 2)

    assert suggestions == [1, 2]
    assert study.dataset.calls == [(raw, 2)]


def test_dataset_adapter_routes_one_metadata_batch() -> None:
    study = _Study()
    updates = [(0, "S01", None), (1, None, "run-02")]

    count = DatasetControllerAdapter(cast(Study, study)).update_metadata_batch(updates)

    assert count == 2
    assert study.dataset.metadata_updates == updates


def test_preprocess_adapter_routes_one_standard_pipeline() -> None:
    study = _Study()

    applied = PreprocessControllerAdapter(cast(Study, study)).apply_standard_pipeline(
        l_freq=4,
        h_freq=40,
        notch_freq=60,
        rate=128,
        ref_channels="average",
        normalization="z score",
    )

    assert applied is True
    assert study.preprocess.standard_options == {
        "l_freq": 4,
        "h_freq": 40,
        "notch_freq": 60,
        "rate": 128,
        "ref_channels": "average",
        "normalization": "z score",
    }


def test_visualization_adapter_encapsulates_notification_batch_state() -> None:
    adapter = VisualizationControllerAdapter(cast(Study, _Study()))

    assert adapter.notifications_deferred is True
    assert adapter.notification_batch_generation == 7
    assert adapter.consume_batched_delivery("saliency_changed", 7) is True
    assert adapter.is_notification_batch_active(7) is True
