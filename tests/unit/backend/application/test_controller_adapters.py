from __future__ import annotations

from typing import Any

from XBrainLab.backend.application.controller_adapters import DatasetControllerAdapter


class _DatasetController:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, int]] = []

    def get_smart_filter_suggestions(self, data: Any, target_count: int) -> list[int]:
        self.calls.append((data, target_count))
        return [1, 2]


class _Study:
    def __init__(self) -> None:
        self.dataset = _DatasetController()

    def get_controller(self, name: str) -> _DatasetController:
        assert name == "dataset"
        return self.dataset


def test_dataset_adapter_preserves_smart_filter_target_file_argument() -> None:
    study = _Study()
    raw = object()

    suggestions = DatasetControllerAdapter(study).get_smart_filter_suggestions(raw, 2)

    assert suggestions == [1, 2]
    assert study.dataset.calls == [(raw, 2)]
