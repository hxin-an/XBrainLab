"""Typed, bounded Preprocess signal publications for UI consumers."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

import numpy as np

from .errors import PreconditionError
from .view_publication import ApplicationViewPublication

DEFAULT_PREPROCESS_PREVIEW_SECONDS = 5.0
MAX_PREPROCESS_PREVIEW_SECONDS = 30.0


class PreprocessSignalState(str, Enum):
    """Presentation state for the signal preview."""

    NO_DATA = "no_data"
    RAW = "raw"
    LOCKED = "locked"


def _copy_array_readonly(value: Any, *, field_name: str) -> np.ndarray:
    source = np.asarray(value)
    if source.dtype.hasobject:
        raise TypeError(f"{field_name} must not contain Python objects")
    immutable_buffer = source.tobytes(order="C")
    return np.frombuffer(immutable_buffer, dtype=source.dtype).reshape(source.shape)


@dataclass(frozen=True, slots=True)
class PreprocessRenderRequest:
    """Request one bounded signal window from an exact application generation."""

    publication_generation: int
    channel_index: int = 0
    start_seconds: float = 0.0
    duration_seconds: float = DEFAULT_PREPROCESS_PREVIEW_SECONDS

    def __post_init__(self) -> None:
        if (
            isinstance(self.publication_generation, bool)
            or not isinstance(self.publication_generation, int)
            or self.publication_generation < 1
        ):
            raise ValueError("publication_generation must be a positive integer")
        if (
            isinstance(self.channel_index, bool)
            or not isinstance(self.channel_index, int)
            or self.channel_index < 0
        ):
            raise ValueError("channel_index must be a non-negative integer")
        for field_name in ("start_seconds", "duration_seconds"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{field_name} must be numeric")
            if not isfinite(float(value)):
                raise ValueError(f"{field_name} must be finite")
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be non-negative")
        if not 0 < self.duration_seconds <= MAX_PREPROCESS_PREVIEW_SECONDS:
            raise ValueError(
                "duration_seconds must be positive and no greater than "
                f"{MAX_PREPROCESS_PREVIEW_SECONDS:g}"
            )


@dataclass(frozen=True, slots=True)
class SignalSeries:
    """One copied signal window in volts with its own sampling frequency."""

    time_seconds: np.ndarray
    values_volts: np.ndarray
    sampling_frequency: float

    def __post_init__(self) -> None:
        time_seconds = _copy_array_readonly(
            self.time_seconds,
            field_name="time_seconds",
        )
        values_volts = _copy_array_readonly(
            self.values_volts,
            field_name="values_volts",
        )
        if time_seconds.ndim != 1 or values_volts.ndim != 1:
            raise ValueError("Signal series arrays must be one-dimensional")
        if time_seconds.size == 0 or time_seconds.shape != values_volts.shape:
            raise ValueError("Signal series arrays must have matching samples")
        sampling_frequency = float(self.sampling_frequency)
        if not isfinite(sampling_frequency) or sampling_frequency <= 0:
            raise ValueError("sampling_frequency must be positive and finite")
        if not np.all(np.isfinite(time_seconds)):
            raise ValueError("Signal time values must be finite")
        object.__setattr__(self, "time_seconds", time_seconds)
        object.__setattr__(self, "values_volts", values_volts)
        object.__setattr__(self, "sampling_frequency", sampling_frequency)


@dataclass(frozen=True, slots=True)
class SignalEvent:
    """One copied annotation intersecting the published signal window."""

    onset_seconds: float
    label: str
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        onset = float(self.onset_seconds)
        duration = float(self.duration_seconds)
        label = str(self.label).strip()
        if not isfinite(onset):
            raise ValueError("Event onset must be finite")
        if not isfinite(duration) or duration < 0:
            raise ValueError("Event duration must be non-negative and finite")
        if not label:
            raise ValueError("Event label cannot be empty")
        object.__setattr__(self, "onset_seconds", onset)
        object.__setattr__(self, "duration_seconds", duration)
        object.__setattr__(self, "label", label)


@dataclass(frozen=True, slots=True)
class PreprocessRenderData:
    """Detached presentation data for the Preprocess signal area."""

    state: PreprocessSignalState
    channels: tuple[str, ...] = ()
    sampling_frequency: float | None = None
    cursor_max_seconds: float = 0.0
    selected_channel_index: int | None = None
    selected_channel_name: str | None = None
    history: tuple[str, ...] = ()
    current: SignalSeries | None = None
    original: SignalSeries | None = None
    events: tuple[SignalEvent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.state, PreprocessSignalState):
            raise TypeError("state must be a PreprocessSignalState")
        channels = tuple(str(channel) for channel in self.channels)
        if any(not channel for channel in channels):
            raise ValueError("Channel names cannot be empty")
        history = tuple(str(item) for item in self.history)
        events = tuple(self.events)
        if any(not isinstance(event, SignalEvent) for event in events):
            raise TypeError("events must contain SignalEvent values")
        cursor_max = float(self.cursor_max_seconds)
        if not isfinite(cursor_max) or cursor_max < 0:
            raise ValueError("cursor_max_seconds must be non-negative and finite")
        sampling_frequency = self.sampling_frequency
        if sampling_frequency is not None:
            sampling_frequency = float(sampling_frequency)
            if not isfinite(sampling_frequency) or sampling_frequency <= 0:
                raise ValueError("sampling_frequency must be positive and finite")
        if self.current is not None and not isinstance(self.current, SignalSeries):
            raise TypeError("current must be a SignalSeries or None")
        if self.original is not None and not isinstance(self.original, SignalSeries):
            raise TypeError("original must be a SignalSeries or None")

        if self.state is PreprocessSignalState.RAW:
            index = self.selected_channel_index
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < len(channels)
            ):
                raise ValueError("RAW render data requires a valid channel index")
            if self.selected_channel_name != channels[index]:
                raise ValueError(
                    "Selected channel name does not match the channel index"
                )
            if sampling_frequency is None or self.current is None:
                raise ValueError("RAW render data requires signal samples and a rate")
        elif self.current is not None or self.original is not None or events:
            raise ValueError("Only RAW render data may contain signal payloads")

        object.__setattr__(self, "channels", channels)
        object.__setattr__(self, "history", history)
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "cursor_max_seconds", cursor_max)
        object.__setattr__(self, "sampling_frequency", sampling_frequency)


@dataclass(frozen=True, slots=True)
class PreprocessRenderPublication:
    """One detached Preprocess payload proven against application truth."""

    request: PreprocessRenderRequest
    generation: int
    data: PreprocessRenderData

    def __post_init__(self) -> None:
        if not isinstance(self.request, PreprocessRenderRequest):
            raise TypeError("request must be a PreprocessRenderRequest")
        if self.generation != self.request.publication_generation:
            raise ValueError("render generation must match its request")
        if not isinstance(self.data, PreprocessRenderData):
            raise TypeError("data must be PreprocessRenderData")


class PreprocessRenderPublisher:
    """Copy one bounded signal window across a verified publication generation."""

    def __init__(
        self,
        *,
        dataset: Any,
        get_publication: Callable[[], ApplicationViewPublication],
    ) -> None:
        self._dataset = dataset
        self._get_publication = get_publication

    def publish(
        self,
        request: PreprocessRenderRequest,
    ) -> PreprocessRenderPublication:
        """Return detached render data or reject stale application identity."""
        if not isinstance(request, PreprocessRenderRequest):
            raise TypeError("request must be a PreprocessRenderRequest")
        before = self._get_publication()
        self._validate_guard(request, before)
        try:
            data = self._copy_render_data(request)
        except PreconditionError:
            raise
        except Exception as exc:
            raise self._target_error(
                "The signal preview could not be prepared"
            ) from exc
        after = self._get_publication()
        if (
            after.generation != before.generation
            or not after.usable
            or not before.usable
        ):
            raise self._stale_error(
                request,
                before_publication=before,
                after_publication=after,
            )
        self._validate_guard(request, after)
        return PreprocessRenderPublication(
            request=request,
            generation=after.generation,
            data=data,
        )

    def _validate_guard(
        self,
        request: PreprocessRenderRequest,
        publication: ApplicationViewPublication,
    ) -> None:
        if (
            not publication.usable
            or publication.generation != request.publication_generation
        ):
            raise self._stale_error(
                request,
                before_publication=publication,
                after_publication=publication,
            )

    def _copy_render_data(
        self,
        request: PreprocessRenderRequest,
    ) -> PreprocessRenderData:
        current_items = list(self._dataset.get_preprocessed_data_list() or [])
        if not current_items:
            return PreprocessRenderData(state=PreprocessSignalState.NO_DATA)

        current_data = current_items[0]
        current_signal = self._mne_signal(current_data)
        channels = self._channels(current_signal)
        history = self._history(current_data)
        if not self._is_raw(current_data):
            return PreprocessRenderData(
                state=PreprocessSignalState.LOCKED,
                channels=channels,
                sampling_frequency=self._sampling_frequency(
                    current_data,
                    current_signal,
                ),
                history=history,
            )
        if not channels:
            raise self._target_error("The selected EEG data has no channels")

        channel_index = (
            request.channel_index if request.channel_index < len(channels) else 0
        )
        channel_name = channels[channel_index]
        sampling_frequency = self._sampling_frequency(current_data, current_signal)
        n_times = self._sample_count(current_signal)
        if n_times <= 0:
            raise self._target_error("The selected EEG data has no signal samples")
        cursor_max = max(0.0, (n_times - 1) / sampling_frequency)
        start_seconds = min(float(request.start_seconds), cursor_max)
        current = self._copy_signal_window(
            current_signal,
            channel_index=channel_index,
            sampling_frequency=sampling_frequency,
            start_seconds=start_seconds,
            duration_seconds=float(request.duration_seconds),
            clamp_start=True,
        )
        original = self._copy_original_window(
            current_data=current_data,
            channel_name=channel_name,
            start_seconds=start_seconds,
            duration_seconds=float(request.duration_seconds),
        )
        events = self._copy_events(
            current_signal,
            start_seconds=float(current.time_seconds[0]),
            end_seconds=float(current.time_seconds[-1]),
        )
        return PreprocessRenderData(
            state=PreprocessSignalState.RAW,
            channels=channels,
            sampling_frequency=sampling_frequency,
            cursor_max_seconds=cursor_max,
            selected_channel_index=channel_index,
            selected_channel_name=channel_name,
            history=history,
            current=current,
            original=original,
            events=events,
        )

    def _copy_original_window(
        self,
        *,
        current_data: Any,
        channel_name: str,
        start_seconds: float,
        duration_seconds: float,
    ) -> SignalSeries | None:
        original_items = list(self._dataset.get_loaded_data_list() or [])
        if not original_items or original_items[0] is current_data:
            return None
        original_data = original_items[0]
        try:
            if not self._is_raw(original_data):
                return None
            original_signal = self._mne_signal(original_data)
            original_channels = self._channels(original_signal)
            if channel_name not in original_channels:
                return None
            original_rate = self._sampling_frequency(
                original_data,
                original_signal,
            )
            return self._copy_signal_window(
                original_signal,
                channel_index=original_channels.index(channel_name),
                sampling_frequency=original_rate,
                start_seconds=start_seconds,
                duration_seconds=duration_seconds,
                clamp_start=False,
            )
        except Exception:
            return None

    @staticmethod
    def _copy_signal_window(
        signal: Any,
        *,
        channel_index: int,
        sampling_frequency: float,
        start_seconds: float,
        duration_seconds: float,
        clamp_start: bool,
    ) -> SignalSeries:
        n_times = PreprocessRenderPublisher._sample_count(signal)
        start_sample = int(start_seconds * sampling_frequency)
        if start_sample >= n_times:
            if not clamp_start:
                raise ValueError("Original signal does not cover the requested window")
            start_sample = max(0, n_times - 1)
        sample_count = max(1, int(duration_seconds * sampling_frequency))
        stop_sample = min(n_times, start_sample + sample_count)
        values = np.asarray(
            signal.get_data(
                start=start_sample,
                stop=stop_sample,
                picks=[channel_index],
            )
        )
        if values.ndim != 2 or values.shape[0] != 1 or values.shape[1] == 0:
            raise ValueError("Signal reader returned an invalid channel window")
        one_channel = values[0]
        times = (
            np.arange(start_sample, start_sample + one_channel.shape[0])
            / sampling_frequency
        )
        return SignalSeries(
            time_seconds=times,
            values_volts=one_channel,
            sampling_frequency=sampling_frequency,
        )

    @staticmethod
    def _copy_events(
        signal: Any,
        *,
        start_seconds: float,
        end_seconds: float,
    ) -> tuple[SignalEvent, ...]:
        annotations = getattr(signal, "annotations", None)
        if annotations is None:
            return ()
        try:
            values: Iterable[Any] = annotations
            copied: list[SignalEvent] = []
            for annotation in values:
                onset = float(annotation["onset"])
                duration = max(float(annotation.get("duration", 0.0)), 0.0)
                annotation_end = onset + duration
                if onset <= end_seconds and annotation_end >= start_seconds:
                    copied.append(
                        SignalEvent(
                            onset_seconds=onset,
                            label=str(annotation["description"]),
                            duration_seconds=duration,
                        )
                    )
            return tuple(copied)
        except (KeyError, TypeError, ValueError, OverflowError):
            return ()

    @staticmethod
    def _mne_signal(data: Any) -> Any:
        get_mne = getattr(data, "get_mne", None)
        if not callable(get_mne):
            raise ValueError("EEG data does not expose its signal")
        signal = get_mne()
        if signal is None:
            raise ValueError("EEG signal is unavailable")
        return signal

    @staticmethod
    def _is_raw(data: Any) -> bool:
        is_raw = getattr(data, "is_raw", None)
        if not callable(is_raw):
            raise ValueError("EEG data does not expose its signal state")
        value = is_raw()
        if type(value) is not bool:
            raise ValueError("EEG signal state is invalid")
        return value

    @staticmethod
    def _channels(signal: Any) -> tuple[str, ...]:
        return tuple(str(channel) for channel in list(signal.ch_names))

    @staticmethod
    def _history(data: Any) -> tuple[str, ...]:
        get_history = getattr(data, "get_preprocess_history", None)
        if not callable(get_history):
            return ()
        value = get_history()
        if value is None:
            return ()
        if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
            return ()
        return tuple(str(item) for item in value)

    @staticmethod
    def _sampling_frequency(data: Any, signal: Any) -> float:
        get_sfreq = getattr(data, "get_sfreq", None)
        value = get_sfreq() if callable(get_sfreq) else signal.info["sfreq"]
        sampling_frequency = float(np.asarray(value).item())
        if not isfinite(sampling_frequency) or sampling_frequency <= 0:
            raise ValueError("EEG sampling frequency is invalid")
        return sampling_frequency

    @staticmethod
    def _sample_count(signal: Any) -> int:
        value = getattr(signal, "n_times", None)
        if value is None:
            times = getattr(signal, "times", None)
            value = len(times) if times is not None else 0
        if isinstance(value, bool):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _target_error(message: str) -> PreconditionError:
        return PreconditionError(
            f"{message}. Refresh Preprocess and try again.",
            diagnostics={
                "preprocess_render_unavailable": True,
                "retryable": True,
            },
        )

    @staticmethod
    def _stale_error(
        request: PreprocessRenderRequest,
        *,
        before_publication: ApplicationViewPublication,
        after_publication: ApplicationViewPublication,
    ) -> PreconditionError:
        return PreconditionError(
            "The signal preview changed before it could be displayed. "
            "Refresh Preprocess and try again.",
            diagnostics={
                "preprocess_render_stale": True,
                "retryable": True,
                "expected_publication_generation": request.publication_generation,
                "publication_generation_before": before_publication.generation,
                "publication_generation_after": after_publication.generation,
                "publication_usable_before": before_publication.usable,
                "publication_usable_after": after_publication.usable,
            },
        )


__all__ = [
    "DEFAULT_PREPROCESS_PREVIEW_SECONDS",
    "MAX_PREPROCESS_PREVIEW_SECONDS",
    "PreprocessRenderData",
    "PreprocessRenderPublication",
    "PreprocessRenderPublisher",
    "PreprocessRenderRequest",
    "PreprocessSignalState",
    "SignalEvent",
    "SignalSeries",
]
