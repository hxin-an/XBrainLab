"""Study-owned preprocessing operations shared by product and UI adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from typing import Any, Protocol

from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.backend.utils.runtime_diagnostics import collect_runtime_diagnostics

ProcessorProvider = Callable[[str], Any]


class PreprocessStudyPort(Protocol):
    """Study state and mutations required by preprocessing operations."""

    @property
    def preprocessed_data_list(self) -> list[Any]: ...

    def set_preprocessed_data_list(
        self,
        preprocessed_data_list: list[Any],
        force_update: bool = False,
    ) -> None: ...

    def reset_preprocess(self, force_update: bool = False) -> None: ...
    def lock_dataset(self) -> None: ...
    def set_channels(
        self,
        chs: list[str],
        positions: list[tuple],
    ) -> None: ...


class PreprocessStateReadPort(Protocol):
    """Preprocess state reads used by application command and snapshot services."""

    def get_preprocessed_data_list(self) -> list[Any]: ...
    def get_runtime_diagnostics(self) -> dict[str, Any]: ...
    def is_epoched(self) -> bool: ...
    def get_channel_names(self) -> list[str]: ...


class PreprocessProductPort(PreprocessStateReadPort, Protocol):
    """Complete preprocess command surface owned by a Study."""

    def apply_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> bool: ...

    def apply_resample(self, rate: float) -> bool: ...
    def apply_normalization(self, method: str) -> bool: ...
    def apply_rereference(self, channels: str | list[str]) -> bool: ...
    def apply_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> bool: ...

    def apply_epoching(
        self,
        baseline: list[float] | tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int] | Sequence[str] | None,
        tmin: float,
        tmax: float,
        allow_boundary_drop: bool = False,
        *,
        event_label_aliases_by_source: Sequence[Mapping[str, str]] | None = None,
    ) -> bool: ...

    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ) -> bool: ...


def _default_processor_provider(name: str) -> Any:
    module = import_module("XBrainLab.backend.preprocessor")
    return getattr(module, name)


class PreprocessStateService(Observable):
    """Own preprocess state transitions without resolving a UI controller."""

    def __init__(
        self,
        study: PreprocessStudyPort,
        *,
        processor_provider: ProcessorProvider = _default_processor_provider,
    ) -> None:
        super().__init__()
        self.study = study
        self._processor_provider = processor_provider

    def get_preprocessed_data_list(self) -> list[Any]:
        return self.study.preprocessed_data_list

    def reset_preprocess(self) -> None:
        self.study.reset_preprocess(force_update=True)
        self.publish_preprocess_changed()

    def is_epoched(self) -> bool:
        data_list = self.study.preprocessed_data_list
        if data_list:
            return not bool(data_list[0].is_raw())
        return False

    def has_data(self) -> bool:
        return bool(self.study.preprocessed_data_list)

    def get_channel_names(self) -> list[str]:
        if self.study.preprocessed_data_list:
            return list(self.study.preprocessed_data_list[0].get_mne().ch_names)
        return []

    def get_first_data(self) -> Any | None:
        if self.study.preprocessed_data_list:
            return self.study.preprocessed_data_list[0]
        return None

    def get_runtime_diagnostics(self) -> dict[str, Any]:
        return collect_runtime_diagnostics(self.study.preprocessed_data_list)

    def apply_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> bool:
        return self._apply_processor(
            self._processor("Filtering"),
            l_freq,
            h_freq,
            notch_freqs=notch_freqs,
        )

    def apply_resample(self, rate: float) -> bool:
        return self._apply_processor(self._processor("Resample"), rate)

    def apply_rereference(self, channels: str | list[str]) -> bool:
        return self._apply_processor(
            self._processor("Rereference"),
            ref_channels=channels,
        )

    def apply_normalization(self, method: str) -> bool:
        return self._apply_processor(self._processor("Normalize"), norm=method)

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
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")

        try:
            working_list = [data.copy() for data in data_list]
            working_list = self._process_working_list(
                working_list,
                self._processor("Filtering"),
                l_freq,
                h_freq,
                notch_freqs=None,
            )
            if notch_freq:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Filtering"),
                    None,
                    None,
                    notch_freqs=[notch_freq],
                )
            if rate:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Resample"),
                    rate,
                )
            if ref_channels:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Rereference"),
                    ref_channels=ref_channels,
                )
            if normalization:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Normalize"),
                    norm=normalization,
                )
        except Exception as exc:
            logger.error("Standard preprocessing pipeline failed: %s", exc)
            raise

        self.study.set_preprocessed_data_list(working_list, force_update=True)
        self.publish_preprocess_changed()
        return True

    def get_unique_events(self) -> list[str]:
        events: set[str] = set()
        for data in self.study.preprocessed_data_list:
            try:
                _, event_ids = data.get_event_list()
                if event_ids:
                    events.update(event_ids.keys())
            except Exception as exc:  # noqa: PERF203
                logger.warning("Failed to get events from preprocessed data: %s", exc)
        return sorted(events)

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
        epoch_options: dict[str, Any] = {}
        if event_label_aliases_by_source is not None:
            epoch_options["event_label_aliases_by_source"] = (
                event_label_aliases_by_source
            )
        result = self._apply_processor(
            self._processor("TimeEpoch"),
            baseline,
            selected_events,
            tmin,
            tmax,
            allow_boundary_drop,
            **epoch_options,
        )
        if result:
            self.study.lock_dataset()
        return result

    def apply_montage(
        self,
        mapped_channels: list[str],
        mapped_positions: list[tuple[float, float, float]],
    ) -> bool:
        self.study.set_channels(mapped_channels, mapped_positions)
        self.publish_preprocess_changed()
        return True

    def publish_preprocess_changed(self) -> bool:
        return self.notify("preprocess_changed")

    def _apply_processor(
        self,
        processor_class: Any,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")

        try:
            working_list = [data.copy() for data in data_list]
            processor = processor_class(working_list)
            result = processor.data_preprocess(*args, **kwargs)
            self.study.set_preprocessed_data_list(result, force_update=True)
            self.publish_preprocess_changed()
        except Exception as exc:
            logger.error("Preprocessing failed: %s", exc)
            raise
        return True

    def _processor(self, name: str) -> Any:
        return self._processor_provider(name)

    @staticmethod
    def _process_working_list(
        working_list: list[Any],
        processor_class: Any,
        *args: Any,
        **kwargs: Any,
    ) -> list[Any]:
        processor = processor_class(working_list)
        return list(processor.data_preprocess(*args, **kwargs))


__all__ = [
    "PreprocessProductPort",
    "PreprocessStateReadPort",
    "PreprocessStateService",
    "PreprocessStudyPort",
    "ProcessorProvider",
]
