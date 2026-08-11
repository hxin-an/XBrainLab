"""UI compatibility controller over the Study-owned preprocessing service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from XBrainLab.backend import preprocessor
from XBrainLab.backend.services.preprocess_state_service import PreprocessStateService
from XBrainLab.backend.utils.observer import Observable


class PreprocessController(Observable):
    """Expose legacy controller methods while sharing product preprocessing truth."""

    def __init__(self, study: Any) -> None:
        super().__init__()
        self.study = study
        shared_service = getattr(study, "preprocess_state_service", None)
        if isinstance(shared_service, PreprocessStateService):
            self._preprocess_state = shared_service
        else:
            self._preprocess_state = PreprocessStateService(
                study,
                processor_provider=lambda name: getattr(preprocessor, name),
            )
        self._preprocess_state.subscribe(
            "preprocess_changed",
            self._relay_preprocess_changed,
        )

    def get_preprocessed_data_list(self) -> list[Any]:
        return self._preprocess_state.get_preprocessed_data_list()

    def reset_preprocess(self) -> None:
        self._preprocess_state.reset_preprocess()

    def is_epoched(self) -> bool:
        return self._preprocess_state.is_epoched()

    def has_data(self) -> bool:
        return self._preprocess_state.has_data()

    def get_channel_names(self) -> list[str]:
        return self._preprocess_state.get_channel_names()

    def get_first_data(self) -> Any | None:
        return self._preprocess_state.get_first_data()

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return self._preprocess_state.get_runtime_diagnostics()

    def apply_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> bool:
        return self._preprocess_state.apply_filter(l_freq, h_freq, notch_freqs)

    def apply_resample(self, sfreq: float) -> bool:
        return self._preprocess_state.apply_resample(sfreq)

    def apply_rereference(self, ref_channels: str | list[str]) -> bool:
        return self._preprocess_state.apply_rereference(ref_channels)

    def apply_normalization(self, method: str) -> bool:
        return self._preprocess_state.apply_normalization(method)

    def apply_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> bool:
        return self._preprocess_state.apply_standard_pipeline(
            l_freq=l_freq,
            h_freq=h_freq,
            notch_freq=notch_freq,
            rate=rate,
            ref_channels=ref_channels,
            normalization=normalization,
        )

    def get_unique_events(self) -> list[str]:
        return self._preprocess_state.get_unique_events()

    def apply_epoching(
        self,
        baseline: list[float] | tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int] | Sequence[str] | None,
        tmin: float,
        tmax: float,
        allow_boundary_drop: bool = False,
        *,
        event_label_aliases_by_source: Sequence[Mapping[str, str]] | None = None,
    ) -> bool:
        epoch_options = {}
        if event_label_aliases_by_source is not None:
            epoch_options["event_label_aliases_by_source"] = (
                event_label_aliases_by_source
            )
        return self._preprocess_state.apply_epoching(
            baseline,
            selected_events,
            tmin,
            tmax,
            allow_boundary_drop,
            **epoch_options,
        )

    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ) -> bool:
        return self._preprocess_state.apply_montage(
            mapped_channels,
            mapped_positions,
        )

    def _relay_preprocess_changed(self) -> bool:
        return self.notify("preprocess_changed")
