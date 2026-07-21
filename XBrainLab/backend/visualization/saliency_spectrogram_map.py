"""Frequency-by-time saliency spectrogram visualiser."""

import logging
from typing import Any

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.colors import Normalize, PowerNorm
from matplotlib.ticker import FuncFormatter
from scipy import signal

from .base import Visualizer

logger = logging.getLogger(__name__)

_ROBUST_LOWER_PERCENTILE = 1.0
_ROBUST_UPPER_PERCENTILE = 99.0
_POWER_SCALE_DYNAMIC_RANGE = 1_000.0


def _compact_colorbar_tick(value: float, _position: int) -> str:
    """Return readable colorbar text for tiny saliency magnitudes."""
    abs_value = abs(value)
    if abs_value == 0:
        return "0"
    if 0.01 <= abs_value < 100:
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value:.1e}"


class SaliencySpectrogramMapViz(Visualizer):
    """Visualizer that generates a frequency-by-time saliency spectrogram.

    The saliency is transformed via STFT and averaged across trials and
    channels, producing one subplot per class label.
    """

    @staticmethod
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

    @classmethod
    def _build_shared_display_scale(
        cls,
        arrays: list[np.ndarray],
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

    def _get_plt(self, method, absolute: bool = False) -> Any:
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
        visible_label_number = len(saliency_by_label)
        rows = 1 if visible_label_number <= self.MIN_LABEL_NUMBER_FOR_MULTI_ROW else 2
        cols = int(np.ceil(visible_label_number / rows))
        spectrogram_by_label = []
        diagnostics: list[dict[str, object]] = []
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
            # SciPy accepts ``None`` to disable boundary extension, but its
            # current type stub only advertises string modes.
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
            saliency = np.mean(np.mean(abs(stft_saliency), axis=0), axis=0)
            if saliency.ndim != 2:
                raise ValueError(
                    f"Spectrogram aggregation produced shape {saliency.shape!r}; "
                    "expected frequency x time.",
                )
            if saliency.shape != (freqs.size, timestamps.size):
                raise ValueError(
                    "Spectrogram axes do not match the rendered matrix: "
                    f"matrix={saliency.shape!r}, frequencies={freqs.size}, "
                    f"times={timestamps.size}.",
                )
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
            spectrogram_by_label.append(
                (
                    label_key,
                    label_name,
                    saliency,
                    freqs,
                    time_centers,
                    time_min,
                    time_max,
                ),
            )

            frequency_stats = [
                {
                    "frequency_hz": float(freq),
                    **self._describe_values(saliency[index]),
                }
                for index, freq in enumerate(freqs)
            ]
            class_diagnostics: dict[str, object] = {
                "label": str(label_name),
                "raw_shape": tuple(raw_saliency.shape),
                "matrix_shape": tuple(saliency.shape),
                **self._describe_values(saliency),
                "frequency_bins": frequency_stats,
            }
            diagnostics.append(class_diagnostics)
            logger.debug("Attribution spectrogram diagnostics: %s", class_diagnostics)

        display_arrays = [entry[2] for entry in spectrogram_by_label]
        shared_norm, colorbar_label, scale_details = self._build_shared_display_scale(
            display_arrays,
        )
        self.spectrogram_diagnostics = tuple(diagnostics)
        self.spectrogram_display_scale = dict(scale_details)
        logger.info("Attribution spectrogram shared display scale: %s", scale_details)
        fig.subplots_adjust(
            left=0.10,
            right=0.86,
            bottom=0.12,
            top=0.84,
            wspace=0.38,
            hspace=0.55,
        )
        fig.suptitle(
            "Attribution magnitude spectrogram",
            color="#cccccc",
            fontsize=10,
        )
        plot_axes = []
        image = None
        for plot_index, (
            _label_key,
            label_name,
            saliency,
            freqs,
            time_centers,
            time_min,
            time_max,
        ) in enumerate(
            spectrogram_by_label,
        ):
            ax = fig.add_subplot(rows, cols, plot_index + 1)
            plot_axes.append(ax)

            cmap = plt.get_cmap("cividis").copy()
            cmap.set_bad("#777777")
            cmap.set_over("#f5e663")
            image = ax.imshow(
                saliency,
                origin="lower",
                interpolation="nearest",
                aspect="auto",
                cmap=cmap,
                norm=shared_norm,
                extent=(
                    time_min,
                    time_max,
                    float(freqs[0]),
                    float(freqs[-1]),
                ),
            )
            tick_count = min(5, time_centers.size)
            tick_label = np.round(
                np.linspace(time_centers[0], time_centers[-1], tick_count),
                2,
            )
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Frequency (Hz)")
            ax.set_xticks(tick_label)
            ax.tick_params(axis="x", labelsize=6)
            ax.set_yticks(freqs[np.where(np.isclose(freqs % 10, 0))])

            ax.set_title(str(label_name))
        if image is not None:
            colorbar = fig.colorbar(
                image,
                ax=plot_axes,
                orientation="vertical",
                fraction=0.035,
                pad=0.04,
                format=FuncFormatter(_compact_colorbar_tick),
                extend=(
                    "max"
                    if int(scale_details.get("over_range_count") or 0) > 0
                    else "neither"
                ),
            )
            colorbar.ax.tick_params(labelsize=7, pad=1)
            colorbar.set_label(colorbar_label, fontsize=8)
        return fig
