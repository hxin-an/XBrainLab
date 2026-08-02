"""Detached dataset-splitting context and preview publication contracts."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from XBrainLab.backend.application.dataset_split_preview import (
    DatasetSplitContextRequest,
    DatasetSplitPreviewPublisher,
    DatasetSplitPreviewRequest,
    DatasetSplitSpecification,
)
from XBrainLab.backend.application.errors import PreconditionError


class _EpochData:
    def __init__(self) -> None:
        self.label_map = {"left": 0, "right": 1}
        self.data = list(range(12))

    def get_subject_map(self) -> dict[str, list[int]]:
        return {"S01": list(range(6)), "S02": list(range(6, 12))}

    def get_session_map(self) -> dict[str, list[int]]:
        return {"session-1": list(range(12))}

    def get_data_length(self) -> int:
        return len(self.data)


class _DatasetState:
    def __init__(self, epoch_data: Any | None) -> None:
        self.epoch_data = epoch_data
        self.read_count = 0

    def get_epoch_data(self) -> Any | None:
        self.read_count += 1
        return self.epoch_data


class _PreviewDataset:
    def __init__(self, name: str, train: int, val: int, test: int) -> None:
        self._row = ("O", name, train, val, test)

    def get_treeview_row_info(self) -> tuple[str, str, int, int, int]:
        return self._row


class _Generator:
    def __init__(self) -> None:
        self.datasets: list[_PreviewDataset] = []
        self.interrupted = False

    def generate(self) -> None:
        self.datasets.extend(
            [
                _PreviewDataset("Fold_0", 8, 2, 2),
                _PreviewDataset("Fold_1", 8, 2, 2),
            ]
        )

    def set_interrupt(self) -> None:
        self.interrupted = True


def _view(generation: int = 4, *, usable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(generation=generation, usable=usable)


def _specification() -> DatasetSplitSpecification:
    return DatasetSplitSpecification.from_payload(
        {
            "train_type": "Full Data",
            "is_cross_validation": True,
            "val_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                    "is_option": True,
                }
            ],
            "test_splitters": [
                {
                    "split_type": "By Trial",
                    "split_unit": "Ratio",
                    "value": "0.2",
                    "is_option": True,
                }
            ],
        }
    )


def test_context_publication_contains_only_detached_split_choices() -> None:
    dataset = _DatasetState(_EpochData())
    publisher = DatasetSplitPreviewPublisher(
        dataset=dataset,
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    publication = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    )

    assert publication.generation == 4
    assert publication.context.epoch_available is True
    assert publication.context.subject_count == 2
    assert publication.context.session_count == 1
    assert publication.context.label_count == 2
    assert publication.context.trial_count == 12
    assert [
        (item.value, item.label) for item in publication.context.subject_choices
    ] == [
        ("S01", "S01"),
        ("S02", "S02"),
    ]
    assert [
        (item.value, item.label) for item in publication.context.session_choices
    ] == [("session-1", "session-1")]
    assert not hasattr(publication.context, "epoch_data")


def test_context_publication_represents_missing_epochs_without_live_payload() -> None:
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(None),
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(),
    )

    publication = publisher.publish_context(
        DatasetSplitContextRequest(publication_generation=4)
    )

    assert publication.context.epoch_available is False
    assert publication.context.trial_count == 0
    assert publication.context.subject_choices == ()
    assert publication.context.session_choices == ()


def test_preview_publication_returns_detached_rows_and_canonical_config() -> None:
    captured_configs: list[Any] = []

    def build_generator(config: Any) -> _Generator:
        captured_configs.append(config)
        return _Generator()

    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(_EpochData()),
        generator_factory=build_generator,
        get_publication=lambda: _view(),
    )
    request = DatasetSplitPreviewRequest(
        request_id="preview-1",
        publication_generation=4,
        specification=_specification(),
    )

    publication = publisher.publish_preview(request)

    assert publication.request == request
    assert publication.generation == 4
    assert [row.name for row in publication.rows] == ["Fold_0", "Fold_1"]
    assert publication.rows[0].train_count == 8
    assert publication.rows[0].validation_count == 2
    assert publication.rows[0].test_count == 2
    assert captured_configs
    assert publisher.cancel_preview("preview-1") is False


def test_stale_context_request_fails_before_reading_epoch_data() -> None:
    dataset = _DatasetState(_EpochData())
    publisher = DatasetSplitPreviewPublisher(
        dataset=dataset,
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: _view(generation=5),
    )

    with pytest.raises(PreconditionError, match="changed"):
        publisher.publish_context(DatasetSplitContextRequest(publication_generation=4))

    assert dataset.read_count == 0


def test_generation_change_discards_preview_rows() -> None:
    publications = iter((_view(4), _view(5)))
    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(_EpochData()),
        generator_factory=lambda _config: _Generator(),
        get_publication=lambda: next(publications),
    )

    with pytest.raises(PreconditionError, match="changed"):
        publisher.publish_preview(
            DatasetSplitPreviewRequest(
                request_id="preview-stale",
                publication_generation=4,
                specification=_specification(),
            )
        )


def test_cancel_preview_interrupts_application_owned_generator() -> None:
    started = threading.Event()

    class BlockingGenerator(_Generator):
        def generate(self) -> None:
            started.set()
            while not self.interrupted:
                time.sleep(0.001)
            raise KeyboardInterrupt

    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(_EpochData()),
        generator_factory=lambda _config: BlockingGenerator(),
        get_publication=lambda: _view(),
    )
    errors: list[BaseException] = []

    def publish() -> None:
        try:
            publisher.publish_preview(
                DatasetSplitPreviewRequest(
                    request_id="preview-cancel",
                    publication_generation=4,
                    specification=_specification(),
                )
            )
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=publish)
    worker.start()
    assert started.wait(timeout=1.0)

    assert publisher.cancel_preview("preview-cancel") is True
    worker.join(timeout=1.0)

    assert worker.is_alive() is False
    assert len(errors) == 1
    assert isinstance(errors[0], PreconditionError)
    assert "cancelled" in str(errors[0]).casefold()


def test_duplicate_active_preview_request_id_is_rejected() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingGenerator(_Generator):
        def generate(self) -> None:
            started.set()
            release.wait(timeout=1.0)
            super().generate()

    publisher = DatasetSplitPreviewPublisher(
        dataset=_DatasetState(_EpochData()),
        generator_factory=lambda _config: BlockingGenerator(),
        get_publication=lambda: _view(),
    )
    request = DatasetSplitPreviewRequest(
        request_id="preview-duplicate",
        publication_generation=4,
        specification=_specification(),
    )
    worker = threading.Thread(target=lambda: publisher.publish_preview(request))
    worker.start()
    assert started.wait(timeout=1.0)

    try:
        with pytest.raises(PreconditionError, match="already active"):
            publisher.publish_preview(request)
    finally:
        release.set()
        worker.join(timeout=1.0)
