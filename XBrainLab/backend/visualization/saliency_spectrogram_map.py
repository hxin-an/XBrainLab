"""Frequency-by-time saliency spectrogram visualiser."""

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
from matplotlib.colors import Normalize, PowerNorm
from scipy import signal

from .base import Visualizer
from .saliency_semantics import (
    SALIENCY_RED_BLUE_CMAP,
    attribution_colormap,
    style_attribution_colorbar,
)

logger = logging.getLogger(__name__)

_ROBUST_LOWER_PERCENTILE = 1.0
_ROBUST_UPPER_PERCENTILE = 99.0
_POWER_SCALE_DYNAMIC_RANGE = 1_000.0


@dataclass(frozen=True)
class _PreparedSpectrogramClass:
    label_key: object
    label_name: str
    magnitude: np.ndarray
    frequencies: np.ndarray
    time_centers: np.ndarray
    time_min: float
    time_max: float
    raw_shape: tuple[int, ...]


@dataclass(frozen=True)
class _PreparedSpectrogram:
    classes: tuple[_PreparedSpectrogramClass, ...]
    diagnostics: tuple[dict[str, object], ...]


@dataclass
class _SpectrogramPreparationVariants:
    raw: _PreparedSpectrogram | None = None
    normalized: _PreparedSpectrogram | None = None


@dataclass
class _SpectrogramPreparationFlight:
    generation: int
    completed: threading.Event = field(default_factory=threading.Event)
    raw: _PreparedSpectrogram | None = None
    normalized: _PreparedSpectrogram | None = None
    error: BaseException | None = None
    invalidated: bool = False
    waiter_count: int = 0


class SaliencySpectrogramPreparationCache:
    """Bound repeated STFT work to one preparation per render lineage."""

    def __init__(self, *, max_lineages: int = 2) -> None:
        if max_lineages < 1:
            raise ValueError("max_lineages must be positive")
        self._max_lineages = max_lineages
        self._lock = threading.RLock()
        self._generation = 0
        self._entries: OrderedDict[Hashable, _SpectrogramPreparationVariants] = (
            OrderedDict()
        )
        self._in_flight: dict[Hashable, _SpectrogramPreparationFlight] = {}

    def _store_locked(
        self,
        *,
        key: Hashable,
        raw: _PreparedSpectrogram,
        normalized: _PreparedSpectrogram | None,
    ) -> _SpectrogramPreparationVariants:
        variants = self._entries.setdefault(
            key,
            _SpectrogramPreparationVariants(),
        )
        if variants.raw is None:
            variants.raw = raw
        if normalized is not None and variants.normalized is None:
            variants.normalized = normalized
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_lineages:
            self._entries.popitem(last=False)
        return variants

    def _release_waiter(
        self,
        *,
        key: Hashable,
        flight: _SpectrogramPreparationFlight,
    ) -> None:
        with self._lock:
            flight.waiter_count -= 1
            if (
                flight.waiter_count == 0
                and flight.completed.is_set()
                and self._in_flight.get(key) is flight
            ):
                del self._in_flight[key]

    def get_or_prepare(
        self,
        *,
        key: Hashable,
        normalized: bool,
        raw_sources: tuple[np.ndarray, ...],
        prepare: Callable[[], _PreparedSpectrogram],
    ) -> _PreparedSpectrogram:
        """Return one display variant while preparing the raw STFT at most once."""
        hash(key)
        joined_flight: _SpectrogramPreparationFlight | None = None
        prepared: _PreparedSpectrogram | None = None
        while True:
            with self._lock:
                cache_generation = self._generation
                variants = self._entries.get(key)
                cached = (
                    (variants.normalized if normalized else variants.raw)
                    if variants is not None
                    else None
                )
                if cached is not None:
                    self._entries.move_to_end(key)
                    return cached

                raw_prepared = variants.raw if variants is not None else None
                if raw_prepared is not None:
                    break

                flight = self._in_flight.get(key)
                if flight is None:
                    owns_flight = True
                    flight = _SpectrogramPreparationFlight(
                        generation=cache_generation,
                    )
                    self._in_flight[key] = flight
                else:
                    owns_flight = False
                    flight.waiter_count += 1

            if owns_flight:
                try:
                    # STFT and diagnostics can be expensive. Keeping this outside
                    # the lock lets clear() invalidate a generation immediately.
                    raw_prepared = prepare()
                    prepared = (
                        _normalize_prepared_spectrogram(
                            raw_prepared,
                            scale=_shared_normalization_scale(raw_sources),
                        )
                        if normalized
                        else raw_prepared
                    )
                except BaseException as error:
                    with self._lock:
                        flight.error = error
                        flight.completed.set()
                        if (
                            flight.waiter_count == 0
                            and self._in_flight.get(key) is flight
                        ):
                            del self._in_flight[key]
                    raise

                with self._lock:
                    flight.raw = raw_prepared
                    if normalized:
                        flight.normalized = prepared
                    if (
                        not flight.invalidated
                        and flight.generation == self._generation
                        and self._in_flight.get(key) is flight
                    ):
                        variants = self._store_locked(
                            key=key,
                            raw=raw_prepared,
                            normalized=prepared if normalized else None,
                        )
                        cached = variants.normalized if normalized else variants.raw
                    else:
                        cached = None
                    flight.completed.set()
                    if flight.waiter_count == 0 and self._in_flight.get(key) is flight:
                        del self._in_flight[key]
                return cached if cached is not None else prepared

            flight.completed.wait()
            with self._lock:
                invalidated = flight.invalidated
                error = flight.error
                raw_prepared = flight.raw
                prepared = flight.normalized if normalized else raw_prepared
            if invalidated:
                self._release_waiter(key=key, flight=flight)
                prepared = None
                continue
            if error is not None:
                self._release_waiter(key=key, flight=flight)
                raise error
            if raw_prepared is None:
                self._release_waiter(key=key, flight=flight)
                raise RuntimeError("Spectrogram preparation completed without a result")
            joined_flight = flight
            break

        try:
            if prepared is None:
                prepared = (
                    _normalize_prepared_spectrogram(
                        raw_prepared,
                        scale=_shared_normalization_scale(raw_sources),
                    )
                    if normalized
                    else raw_prepared
                )

            with self._lock:
                if cache_generation != self._generation:
                    return prepared
                variants = self._store_locked(
                    key=key,
                    raw=raw_prepared,
                    normalized=prepared if normalized else None,
                )
                cached = variants.normalized if normalized else variants.raw
                return cached if cached is not None else prepared
        finally:
            if joined_flight is not None:
                self._release_waiter(key=key, flight=joined_flight)

    def clear(self) -> None:
        """Release prepared display arrays without waiting for active STFT work."""
        with self._lock:
            self._generation += 1
            self._entries.clear()
            flights = tuple(self._in_flight.values())
            self._in_flight.clear()
            for flight in flights:
                flight.invalidated = True
                flight.completed.set()


def _describe_values(values: np.ndarray) -> dict[str, float | int]:
    flat = np.asarray(values).ravel()
    finite = flat[np.isfinite(flat)]
    if finite.size:
        percentiles = np.percentile(finite, [1, 5, 50, 95, 99])
        minimum = float(np.min(finite))
        maximum = float(np.max(finite))
    else:
        percentiles = np.full(5, np.nan)
        minimum = maximum = float("nan")
    return {
        "min": minimum,
        "max": maximum,
        "median": float(percentiles[2]),
        "p1": float(percentiles[0]),
        "p5": float(percentiles[1]),
        "p95": float(percentiles[3]),
        "p99": float(percentiles[4]),
        "non_zero_ratio": float(np.count_nonzero(finite) / finite.size)
        if finite.size
        else 0.0,
        "zero_ratio": float(np.count_nonzero(finite == 0) / finite.size)
        if finite.size
        else 0.0,
        "nan_count": int(np.count_nonzero(np.isnan(flat))),
        "inf_count": int(np.count_nonzero(np.isinf(flat))),
        "finite_count": int(finite.size),
    }


def _prepared_spectrogram(
    classes: tuple[_PreparedSpectrogramClass, ...],
) -> _PreparedSpectrogram:
    diagnostics: list[dict[str, object]] = []
    for prepared_class in classes:
        frequency_stats = [
            {
                "frequency_hz": float(frequency),
                **_describe_values(prepared_class.magnitude[index]),
            }
            for index, frequency in enumerate(prepared_class.frequencies)
        ]
        diagnostics.append(
            {
                "label": prepared_class.label_name,
                "raw_shape": prepared_class.raw_shape,
                "matrix_shape": tuple(prepared_class.magnitude.shape),
                **_describe_values(prepared_class.magnitude),
                "frequency_bins": frequency_stats,
            },
        )
    return _PreparedSpectrogram(classes=classes, diagnostics=tuple(diagnostics))


def _shared_normalization_scale(values: tuple[np.ndarray, ...]) -> float:
    scale = max(float(np.max(np.abs(array), initial=0.0)) for array in values)
    return scale


def _normalize_prepared_spectrogram(
    prepared: _PreparedSpectrogram,
    *,
    scale: float,
) -> _PreparedSpectrogram:
    if scale <= np.finfo(np.float64).eps:
        return prepared

    normalized_classes = []
    for prepared_class in prepared.classes:
        magnitude = prepared_class.magnitude
        divisor = np.asarray(scale, dtype=magnitude.dtype)
        normalized = np.divide(magnitude, divisor)
        normalized.setflags(write=False)
        normalized_classes.append(
            _PreparedSpectrogramClass(
                label_key=prepared_class.label_key,
                label_name=prepared_class.label_name,
                magnitude=normalized,
                frequencies=prepared_class.frequencies,
                time_centers=prepared_class.time_centers,
                time_min=prepared_class.time_min,
                time_max=prepared_class.time_max,
                raw_shape=prepared_class.raw_shape,
            ),
        )
    return _prepared_spectrogram(tuple(normalized_classes))


class SaliencySpectrogramMapViz(Visualizer):
    """Visualizer that generates a frequency-by-time saliency spectrogram.

    The saliency is transformed via STFT and averaged across trials and
    channels, producing one subplot per class label.
    """

    @staticmethod
    def _describe_values(values: np.ndarray) -> dict[str, float | int]:
        return _describe_values(values)

    @classmethod
    def _build_shared_display_scale(
        cls,
        arrays: list[np.ndarray],
        *,
        normalized: bool = False,
    ) -> tuple[Normalize, str, dict[str, float | int | str]]:
        finite_parts = []
        for array in arrays:
            flat = np.asarray(array).ravel()
            finite_parts.append(flat[np.isfinite(flat)])
        finite_parts = [part for part in finite_parts if part.size]
        if not finite_parts:
            raise ValueError("Spectrogram magnitude contains no finite values.")
        pooled = np.concatenate(finite_parts)
        if float(np.min(pooled)) < -1e-12:
            raise ValueError("Spectrogram magnitude unexpectedly contains negatives.")

        if normalized:
            over_range_count = int(np.count_nonzero(pooled > 1.0))
            return (
                Normalize(vmin=0.0, vmax=1.0, clip=False),
                "Normalized attribution magnitude",
                {
                    "scale": "normalized",
                    "vmin": 0.0,
                    "vmax": 1.0,
                    "data_max": float(np.max(pooled)),
                    "upper_percentile": 100.0,
                    "over_range_count": over_range_count,
                    "over_range_ratio": float(over_range_count / pooled.size),
                    "lower_reference": 0.0,
                    "dynamic_range": 1.0,
                },
            )

        epsilon = float(np.finfo(float).eps)
        data_max = float(np.max(pooled))
        upper = float(np.percentile(pooled, _ROBUST_UPPER_PERCENTILE))
        if not np.isfinite(upper) or upper <= epsilon:
            upper = max(data_max, epsilon)
        over_range_count = int(np.count_nonzero(pooled > upper))
        over_range_ratio = float(over_range_count / pooled.size)
        positive = pooled[pooled > epsilon]
        if positive.size:
            lower_reference = float(
                np.percentile(positive, _ROBUST_LOWER_PERCENTILE),
            )
            dynamic_range = upper / max(lower_reference, epsilon)
        else:
            lower_reference = 0.0
            dynamic_range = 1.0

        if dynamic_range >= _POWER_SCALE_DYNAMIC_RANGE:
            norm: Normalize = PowerNorm(
                gamma=0.5,
                vmin=0.0,
                vmax=upper,
                clip=False,
            )
            label = "Attribution magnitude (power, shared p99 scale)"
            scale_name = "power"
        else:
            norm = Normalize(vmin=0.0, vmax=upper, clip=False)
            label = "Attribution magnitude (shared p99 scale)"
            scale_name = "linear"
        return (
            norm,
            label,
            {
                "scale": scale_name,
                "vmin": 0.0,
                "vmax": upper,
                "data_max": data_max,
                "upper_percentile": _ROBUST_UPPER_PERCENTILE,
                "over_range_count": over_range_count,
                "over_range_ratio": over_range_ratio,
                "lower_reference": lower_reference,
                "dynamic_range": float(dynamic_range),
            },
        )

    def _prepare_spectrogram(
        self,
        saliency_by_label: list[tuple[object, str, np.ndarray]],
        *,
        sfreq: float,
    ) -> _PreparedSpectrogram:
        prepared_classes: list[_PreparedSpectrogramClass] = []
        for label_key, label_name, raw_values in saliency_by_label:
            raw_saliency = np.asarray(raw_values)
            if raw_saliency.ndim != 3:
                raise ValueError(
                    "Saliency spectrogram expects epochs x channels x samples; "
                    f"received shape {raw_saliency.shape!r} for {label_name!r}.",
                )
            if not np.all(np.isfinite(raw_saliency)):
                raise ValueError(
                    f"Saliency for {label_name!r} contains NaN or infinite values.",
                )
            sample_count = int(raw_saliency.shape[-1])
            if sample_count < 2:
                raise ValueError(
                    "At least two epoch samples are required for a spectrogram.",
                )
            segment_samples = min(max(2, round(sfreq)), sample_count)
            overlap_samples = min(segment_samples // 2, segment_samples - 1)
            boundary_mode: Any = None
            freqs, timestamps, stft_saliency = signal.stft(
                raw_saliency,
                fs=sfreq,
                axis=-1,
                nperseg=segment_samples,
                noverlap=overlap_samples,
                boundary=boundary_mode,
                padded=False,
            )
            magnitude = np.mean(np.mean(abs(stft_saliency), axis=0), axis=0)
            if magnitude.ndim != 2:
                raise ValueError(
                    f"Spectrogram aggregation produced shape {magnitude.shape!r}; "
                    "expected frequency x time.",
                )
            if magnitude.shape != (freqs.size, timestamps.size):
                raise ValueError(
                    "Spectrogram axes do not match the rendered matrix: "
                    f"matrix={magnitude.shape!r}, frequencies={freqs.size}, "
                    f"times={timestamps.size}.",
                )
            magnitude.setflags(write=False)
            epoch_start = float(getattr(self.epoch_data, "tmin", 0.0))
            time_centers = epoch_start + timestamps
            if time_centers.size == 1:
                half_bin_width = segment_samples / (2 * sfreq)
                time_min = float(time_centers[0] - half_bin_width)
                time_max = float(time_centers[0] + half_bin_width)
            else:
                time_min = float(
                    time_centers[0] - (time_centers[1] - time_centers[0]) / 2,
                )
                time_max = float(
                    time_centers[-1] + (time_centers[-1] - time_centers[-2]) / 2,
                )
            prepared_classes.append(
                _PreparedSpectrogramClass(
                    label_key=label_key,
                    label_name=str(label_name),
                    magnitude=magnitude,
                    frequencies=freqs,
                    time_centers=time_centers,
                    time_min=time_min,
                    time_max=time_max,
                    raw_shape=tuple(raw_saliency.shape),
                ),
            )
        return _prepared_spectrogram(tuple(prepared_classes))

    def _get_plt(
        self,
        method,
        absolute: bool = False,
        *,
        display_normalized: bool | None = None,
        preparation_cache: SaliencySpectrogramPreparationCache | None = None,
        preparation_key: Hashable | None = None,
        selected_label_key: object | None = None,
        display_mode: str = "all",
    ) -> Any:
        """Render the saliency spectrogram figure.

        Args:
            method: Name of the saliency method (e.g. ``"Gradient"``).
            absolute: Accepted for interface consistency with sibling
                visualisers but currently unused by this implementation.

        Returns:
            matplotlib.figure.Figure: The rendered spectrogram figure.

        """
        del absolute  # STFT magnitude is non-negative by definition.
        sfreq = float(self.epoch_data.get_model_args()["sfreq"])
        if sfreq <= 0:
            raise ValueError("Sampling frequency must be positive for a spectrogram.")
        if self.fig is None:
            raise RuntimeError("Visualizer figure was not initialized")
        fig = self.fig
        saliency_by_label = self.iter_saliency_by_label(method)
        if not saliency_by_label:
            ax = fig.gca()
            ax.text(0.5, 0.5, "No saliency data for this run.", ha="center")
            ax.set_axis_off()
            return fig
        raw_sources = tuple(np.asarray(entry[2]) for entry in saliency_by_label)

        def prepare() -> _PreparedSpectrogram:
            return self._prepare_spectrogram(
                saliency_by_label,
                sfreq=sfreq,
            )

        normalized = (
            bool(getattr(self.epoch_data, "normalized", False))
            if display_normalized is None
            else bool(display_normalized)
        )
        if preparation_cache is not None and preparation_key is not None:
            prepared = preparation_cache.get_or_prepare(
                key=preparation_key,
                normalized=normalized,
                raw_sources=raw_sources,
                prepare=prepare,
            )
        else:
            prepared = prepare()

        display_arrays = [entry.magnitude for entry in prepared.classes]
        shared_norm, colorbar_label, scale_details = self._build_shared_display_scale(
            display_arrays,
            normalized=normalized,
        )
        self.spectrogram_diagnostics = prepared.diagnostics
        self.spectrogram_display_scale = dict(scale_details)
        if display_mode not in {"all", "single"}:
            raise ValueError("display_mode must be 'all' or 'single'")
        plotted_classes = prepared.classes
        if display_mode == "single":
            plotted_classes = tuple(
                item
                for item in prepared.classes
                if item.label_key == selected_label_key
            )
            if not plotted_classes:
                raise ValueError("Selected saliency class is not available.")
        visible_label_number = len(plotted_classes)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        if display_mode == "all":
            cast(Any, fig)._xbrainlab_min_canvas_height = max(420, rows * 240)
        for diagnostic in prepared.diagnostics:
            logger.debug("Attribution spectrogram diagnostics: %s", diagnostic)
        logger.info(
            "Attribution spectrogram shared display scale: "
            "scale=%s vmin=%.6g vmax=%.6g over_range_ratio=%.6g",
            str(scale_details["scale"]),
            float(scale_details["vmin"]),
            float(scale_details["vmax"]),
            float(scale_details["over_range_ratio"]),
        )
        display_cmap = attribution_colormap(SALIENCY_RED_BLUE_CMAP)
        fig.subplots_adjust(
            left=0.10,
            right=0.86,
            bottom=0.12,
            top=0.92,
            wspace=0.38,
            hspace=0.55,
        )
        grid = fig.add_gridspec(
            rows,
            cols + 1,
            width_ratios=[1.0] * cols + [0.075],
            wspace=0.65,
            hspace=0.55,
        )
        image = None
        for plot_index, prepared_class in enumerate(plotted_classes):
            ax = fig.add_subplot(grid[plot_index // cols, plot_index % cols])

            image = ax.imshow(
                prepared_class.magnitude,
                origin="lower",
                interpolation="nearest",
                aspect="auto",
                cmap=display_cmap,
                norm=shared_norm,
                extent=(
                    prepared_class.time_min,
                    prepared_class.time_max,
                    float(prepared_class.frequencies[0]),
                    float(prepared_class.frequencies[-1]),
                ),
            )
            tick_count = min(5, prepared_class.time_centers.size)
            tick_label = np.round(
                np.linspace(
                    prepared_class.time_centers[0],
                    prepared_class.time_centers[-1],
                    tick_count,
                ),
                2,
            )
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Frequency (Hz)")
            ax.set_xticks(tick_label)
            ax.tick_params(axis="x", labelsize=6)
            freqs = prepared_class.frequencies
            ax.set_yticks(freqs[np.where(np.isclose(freqs % 10, 0))])

            ax.set_title(prepared_class.label_name)
        if image is not None:
            colorbar_axis = fig.add_subplot(grid[:, -1])
            colorbar = fig.colorbar(
                image,
                cax=colorbar_axis,
                orientation="vertical",
                extend=(
                    "max"
                    if int(scale_details.get("over_range_count") or 0) > 0
                    else "neither"
                ),
            )
            style_attribution_colorbar(colorbar, label=colorbar_label)
        return fig
