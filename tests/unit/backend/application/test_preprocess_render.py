from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.preprocess_render import (
    PreprocessRenderPublisher,
    PreprocessRenderRequest,
    PreprocessSignalState,
)


class _Signal:
    def __init__(
        self,
        data: np.ndarray,
        *,
        sfreq: float,
        channels: tuple[str, ...] = ("C3", "C4"),
        annotations: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.data = data
        self.info = {"sfreq": sfreq}
        self.ch_names = list(channels)
        self.annotations = list(annotations)
        self.n_times = int(data.shape[-1])
        self.reads: list[tuple[int, int, tuple[int, ...]]] = []

    def get_data(
        self,
        *,
        start: int,
        stop: int,
        picks: list[int],
    ) -> np.ndarray:
        self.reads.append((start, stop, tuple(picks)))
        return self.data[picks, start:stop]


class _Data:
    def __init__(
        self,
        signal: _Signal,
        *,
        raw: bool = True,
        history: tuple[str, ...] = (),
    ) -> None:
        self.signal = signal
        self.raw = raw
        self.history = list(history)

    def is_raw(self) -> bool:
        return self.raw

    def get_mne(self) -> _Signal:
        return self.signal

    def get_sfreq(self) -> float:
        return float(self.signal.info["sfreq"])

    def get_preprocess_history(self) -> list[str]:
        return self.history


class _Dataset:
    def __init__(
        self,
        *,
        current: list[_Data] | None = None,
        original: list[_Data] | None = None,
    ) -> None:
        self.current = current or []
        self.original = original or []
        self.current_reads = 0

    def get_preprocessed_data_list(self) -> list[_Data]:
        self.current_reads += 1
        return list(self.current)

    def get_loaded_data_list(self) -> list[_Data]:
        return list(self.original)


def _publication(generation: int = 3, *, usable: bool = True) -> Any:
    return SimpleNamespace(generation=generation, usable=usable)


def test_raw_publication_is_bounded_detached_and_generation_bound() -> None:
    current_values = np.arange(2000, dtype=np.float64).reshape(2, 1000)
    original_values = np.arange(1000, dtype=np.float64).reshape(2, 500)
    current_signal = _Signal(
        current_values,
        sfreq=100.0,
        annotations=(
            {"onset": 0.5, "duration": 0.0, "description": "before"},
            {"onset": 1.5, "duration": 0.4, "description": "cue"},
            {"onset": 8.0, "duration": 0.0, "description": "after"},
        ),
    )
    original_signal = _Signal(original_values, sfreq=50.0)
    dataset = _Dataset(
        current=[_Data(current_signal, history=("Band-pass",))],
        original=[_Data(original_signal)],
    )
    publisher = PreprocessRenderPublisher(
        dataset=dataset,
        get_publication=lambda: _publication(),
    )
    request = PreprocessRenderRequest(
        publication_generation=3,
        channel_index=1,
        start_seconds=1.0,
        duration_seconds=2.0,
    )

    publication = publisher.publish(request)

    assert publication.request == request
    assert publication.generation == 3
    assert publication.data.state is PreprocessSignalState.RAW
    assert publication.data.channels == ("C3", "C4")
    assert publication.data.selected_channel_index == 1
    assert publication.data.selected_channel_name == "C4"
    assert publication.data.sampling_frequency == 100.0
    assert publication.data.cursor_max_seconds == pytest.approx(9.99)
    assert publication.data.history == ("Band-pass",)
    assert current_signal.reads == [(100, 300, (1,))]
    assert original_signal.reads == [(50, 150, (1,))]

    current = publication.data.current
    original = publication.data.original
    assert current is not None
    assert original is not None
    assert current.sampling_frequency == 100.0
    assert original.sampling_frequency == 50.0
    assert current.time_seconds[[0, -1]].tolist() == pytest.approx([1.0, 2.99])
    assert original.time_seconds[[0, -1]].tolist() == pytest.approx([1.0, 2.98])
    assert current.values_volts.flags.writeable is False
    assert original.values_volts.flags.writeable is False
    assert not np.shares_memory(current.values_volts, current_values)
    assert not np.shares_memory(original.values_volts, original_values)
    assert [
        (event.onset_seconds, event.label) for event in publication.data.events
    ] == [(1.5, "cue")]

    current_values[1, 100] = -999.0
    dataset.current[0].history.append("Mutated")
    assert current.values_volts[0] != -999.0
    assert publication.data.history == ("Band-pass",)
    with pytest.raises(ValueError):
        current.values_volts[0] = 0.0
    with pytest.raises(ValueError):
        current.values_volts.setflags(write=True)


def test_no_data_publication_has_no_signal_payload() -> None:
    publisher = PreprocessRenderPublisher(
        dataset=_Dataset(),
        get_publication=lambda: _publication(),
    )

    publication = publisher.publish(PreprocessRenderRequest(publication_generation=3))

    assert publication.data.state is PreprocessSignalState.NO_DATA
    assert publication.data.channels == ()
    assert publication.data.current is None
    assert publication.data.original is None
    assert publication.data.events == ()


def test_epoched_data_publishes_locked_state_without_reading_samples() -> None:
    signal = _Signal(np.ones((2, 100)), sfreq=100.0)
    data = _Data(signal, raw=False, history=("Epoching",))
    publisher = PreprocessRenderPublisher(
        dataset=_Dataset(current=[data], original=[data]),
        get_publication=lambda: _publication(),
    )

    publication = publisher.publish(PreprocessRenderRequest(publication_generation=3))

    assert publication.data.state is PreprocessSignalState.LOCKED
    assert publication.data.channels == ("C3", "C4")
    assert publication.data.history == ("Epoching",)
    assert publication.data.current is None
    assert signal.reads == []


def test_outdated_channel_index_falls_back_to_first_channel() -> None:
    signal = _Signal(np.ones((2, 100)), sfreq=100.0)
    publisher = PreprocessRenderPublisher(
        dataset=_Dataset(current=[_Data(signal)]),
        get_publication=lambda: _publication(),
    )

    publication = publisher.publish(
        PreprocessRenderRequest(
            publication_generation=3,
            channel_index=99,
        )
    )

    assert publication.data.selected_channel_index == 0
    assert publication.data.selected_channel_name == "C3"
    assert signal.reads == [(0, 100, (0,))]


def test_stale_generation_fails_before_reading_domain_data() -> None:
    dataset = _Dataset(current=[_Data(_Signal(np.ones((1, 10)), sfreq=10.0))])
    publisher = PreprocessRenderPublisher(
        dataset=dataset,
        get_publication=lambda: _publication(generation=4),
    )

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(PreprocessRenderRequest(publication_generation=3))

    assert dataset.current_reads == 0
    assert exc_info.value.diagnostics["preprocess_render_stale"] is True
    assert exc_info.value.diagnostics["publication_generation_after"] == 4


def test_publication_change_discards_copied_signal() -> None:
    signal = _Signal(np.ones((1, 10)), sfreq=10.0)
    publications = iter((_publication(3), _publication(4)))
    publisher = PreprocessRenderPublisher(
        dataset=_Dataset(current=[_Data(signal)]),
        get_publication=lambda: next(publications),
    )

    with pytest.raises(PreconditionError) as exc_info:
        publisher.publish(PreprocessRenderRequest(publication_generation=3))

    assert signal.reads == [(0, 10, (0,))]
    assert exc_info.value.diagnostics["preprocess_render_stale"] is True
    assert exc_info.value.diagnostics["publication_generation_before"] == 3
    assert exc_info.value.diagnostics["publication_generation_after"] == 4
