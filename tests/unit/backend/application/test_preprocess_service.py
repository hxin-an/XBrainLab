"""Focused tests for preprocessing and epoch command handlers."""

from __future__ import annotations

from typing import Any

import pytest

from XBrainLab.backend.application.commands import (
    CreateEpochCommand,
    PreprocessCommand,
    PreprocessOperation,
)
from XBrainLab.backend.application.errors import (
    ConfirmationRequiredError,
    PreconditionError,
)
from XBrainLab.backend.application.preprocess_service import (
    PreprocessCommandService,
)


class _BatchNotifications:
    def __init__(self, controller: _PreprocessController) -> None:
        self.controller = controller

    def __enter__(self) -> None:
        self.controller.events.append(("batch_enter", None))

    def __exit__(self, *_exc: object) -> None:
        self.controller.events.append(("batch_exit", None))


class _PreprocessController:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def apply_filter(
        self,
        low_freq: float | None,
        high_freq: float | None,
        notch_freqs: list[float] | None,
    ) -> None:
        self.events.append(("filter", (low_freq, high_freq, notch_freqs)))

    def apply_resample(self, rate: float) -> None:
        self.events.append(("resample", rate))

    def apply_normalization(self, method: str) -> None:
        self.events.append(("normalize", method))

    def apply_rereference(self, channels: str | list[str]) -> None:
        self.events.append(("rereference", channels))

    def apply_epoching(
        self,
        baseline: tuple[float, float] | None,
        event_ids: dict[str, int] | list[str] | None,
        t_min: float,
        t_max: float,
    ) -> None:
        self.events.append(("epoch", (baseline, event_ids, t_min, t_max)))

    def batch_notifications(self) -> _BatchNotifications:
        return _BatchNotifications(self)


class _DatasetController:
    def __init__(self) -> None:
        self.selected_channels: list[str] | None = None

    def apply_channel_selection(self, channels: list[str]) -> None:
        self.selected_channels = channels


def _service() -> tuple[
    PreprocessCommandService,
    _PreprocessController,
    _DatasetController,
]:
    preprocess = _PreprocessController()
    dataset = _DatasetController()
    return (
        PreprocessCommandService(preprocess=preprocess, dataset=dataset),
        preprocess,
        dataset,
    )


def test_preprocess_service_applies_core_operations() -> None:
    service, preprocess, dataset = _service()

    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.BANDPASS,
                low_freq=1.0,
                high_freq=40.0,
                notch_freq=50.0,
            ),
        )
        == "Applied bandpass filter (1.0-40.0 Hz)."
    )
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.REREFERENCE,
                method="average",
            ),
        )
        == "Applied reference: average."
    )
    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.SELECT_CHANNELS,
                channels=["C3", "C4"],
            ),
        )
        == "Selected 2 channel(s)."
    )

    assert preprocess.events == [
        ("filter", (1.0, 40.0, [50.0])),
        ("rereference", "average"),
    ]
    assert dataset.selected_channels == ["C3", "C4"]


def test_preprocess_service_applies_standard_preprocess_in_batch() -> None:
    service, preprocess, _dataset = _service()

    assert (
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.STANDARD,
                notch_freq=60.0,
                rate=128,
                method="z score",
            ),
        )
        == "Standard preprocessing applied."
    )

    assert preprocess.events == [
        ("batch_enter", None),
        ("filter", (4, 40, None)),
        ("filter", (None, None, [60.0])),
        ("resample", 128),
        ("normalize", "z score"),
        ("batch_exit", None),
    ]


def test_preprocess_service_creates_epoch() -> None:
    service, preprocess, _dataset = _service()

    assert (
        service.handle_create_epoch(
            CreateEpochCommand(
                baseline=(0.0, 0.2),
                event_ids={"left": 1},
                t_min=-0.5,
                t_max=1.5,
            ),
        )
        == "Created epochs from -0.5s to 1.5s."
    )

    assert preprocess.events == [
        ("epoch", ((0.0, 0.2), {"left": 1}, -0.5, 1.5)),
    ]


def test_preprocess_service_preserves_safety_boundaries() -> None:
    service, _preprocess, _dataset = _service()

    with pytest.raises(PreconditionError, match="low_freq is required"):
        service.handle_preprocess(
            PreprocessCommand(operation=PreprocessOperation.BANDPASS, high_freq=40.0),
        )

    with pytest.raises(ConfirmationRequiredError, match="set_montage requires UI"):
        service.handle_preprocess(
            PreprocessCommand(
                operation=PreprocessOperation.SET_MONTAGE,
                montage_name="standard_1020",
            ),
        )
