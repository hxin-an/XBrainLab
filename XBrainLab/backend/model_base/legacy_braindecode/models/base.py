# Adapted from braindecode 1.6.1.
#
# Authors: Pierre Guetschel
#          Maciej Sliwowski
#
# License: BSD-3-Clause
"""Minimal local signal-contract mixin for vendored model implementations.

The upstream Hub, configuration serialization, docstring metaclass, and model
discovery features are deliberately excluded. XBrainLab owns model selection,
artifact persistence, and provider admission outside this compatibility module.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

import torch


class EEGModuleMixin:
    """Store and infer the signal dimensions shared by Braindecode models."""

    mapping: dict[str, str] | None = None

    def __init__(
        self,
        n_outputs: int | None = None,
        n_chans: int | None = None,
        chs_info: list[dict[str, Any]] | None = None,
        n_times: int | None = None,
        input_window_seconds: float | None = None,
        sfreq: float | None = None,
    ) -> None:
        if n_chans is not None and chs_info is not None and len(chs_info) != n_chans:
            raise ValueError(f"{n_chans=} different from {chs_info=} length")
        if (
            n_times is not None
            and input_window_seconds is not None
            and sfreq is not None
            and n_times != round(input_window_seconds * sfreq)
        ):
            raise ValueError(
                f"{n_times=} different from {input_window_seconds=} * {sfreq=}"
            )

        self._input_window_seconds = input_window_seconds
        self._chs_info = chs_info
        self._n_outputs = n_outputs
        self._n_chans = n_chans
        self._n_times = n_times
        self._sfreq = sfreq
        super().__init__()

    @property
    def n_outputs(self) -> int:
        if self._n_outputs is None:
            raise ValueError("n_outputs not specified.")
        return self._n_outputs

    @property
    def n_chans(self) -> int:
        if self._n_chans is None and self._chs_info is not None:
            return len(self._chs_info)
        if self._n_chans is None:
            raise ValueError(
                "n_chans could not be inferred. Either specify n_chans or chs_info."
            )
        return self._n_chans

    @property
    def chs_info(self) -> list[dict[str, Any]]:
        if self._chs_info is None:
            raise ValueError("chs_info not specified.")
        return self._chs_info

    @property
    def n_times(self) -> int:
        if (
            self._n_times is None
            and self._input_window_seconds is not None
            and self._sfreq is not None
        ):
            return round(self._input_window_seconds * self._sfreq)
        if self._n_times is None:
            raise ValueError(
                "n_times could not be inferred. Either specify n_times or "
                "input_window_seconds and sfreq."
            )
        return self._n_times

    @property
    def input_window_seconds(self) -> float:
        if (
            self._input_window_seconds is None
            and self._n_times is not None
            and self._sfreq is not None
        ):
            return float(self._n_times / self._sfreq)
        if self._input_window_seconds is None:
            raise ValueError(
                "input_window_seconds could not be inferred. Either specify "
                "input_window_seconds or n_times and sfreq."
            )
        return self._input_window_seconds

    @property
    def sfreq(self) -> float:
        if (
            self._sfreq is None
            and self._input_window_seconds is not None
            and self._n_times is not None
        ):
            return float(self._n_times / self._input_window_seconds)
        if self._sfreq is None:
            raise ValueError(
                "sfreq could not be inferred. Either specify sfreq or "
                "input_window_seconds and n_times."
            )
        return self._sfreq

    @property
    def input_shape(self) -> tuple[int, int, int]:
        return (1, self.n_chans, self.n_times)

    def get_output_shape(self) -> tuple[int, ...]:
        with torch.inference_mode():
            parameter = next(self.parameters())  # type: ignore[attr-defined]
            output = self.forward(  # type: ignore[attr-defined]
                torch.zeros(
                    self.input_shape,
                    dtype=parameter.dtype,
                    device=parameter.device,
                )
            )
        return tuple(output.shape)

    def load_state_dict(self, state_dict, *args, **kwargs):
        mapping = self.mapping or {}
        translated = OrderedDict(
            (mapping.get(key, key), value) for key, value in state_dict.items()
        )
        return super().load_state_dict(  # type: ignore[attr-defined]
            translated, *args, **kwargs
        )
