"""Study-owned preprocessing operations shared by product and UI adapters."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from XBrainLab.backend.application.owned_work import (
    OwnedOperationCancelledError,
    owned_work_checkpoint,
    owned_work_commit_boundary,
)
from XBrainLab.backend.utils.logger import logger
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.backend.utils.runtime_diagnostics import collect_runtime_diagnostics

ProcessorProvider = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class PreparedPreprocessData:
    """Detached preprocessing result bound to one source-list identity."""

    source_identity: tuple[int, ...]
    data: tuple[Any, ...]
    lock_dataset: bool = False

    def __post_init__(self) -> None:
        if not self.source_identity:
            raise ValueError("Prepared preprocessing requires source EEG data.")
        if len(self.source_identity) != len(self.data):
            raise ValueError("Prepared preprocessing changed the recording count.")


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


class _DetachedPreprocessStudy:
    """Private holder that cannot publish prepared work into the live Study."""

    def __init__(self, preprocessed_data: Sequence[Any]) -> None:
        self.preprocessed_data_list = list(preprocessed_data)

    def set_preprocessed_data_list(
        self,
        preprocessed_data_list: list[Any],
        force_update: bool = False,
    ) -> None:
        del preprocessed_data_list, force_update
        raise RuntimeError("Detached preprocessing holders cannot publish state.")

    def reset_preprocess(self, force_update: bool = False) -> None:
        del force_update
        raise RuntimeError("Detached preprocessing holders cannot reset state.")

    def lock_dataset(self) -> None:
        raise RuntimeError("Detached preprocessing holders cannot lock datasets.")

    def set_channels(
        self,
        chs: list[str],
        positions: list[tuple],
    ) -> None:
        del chs, positions
        raise RuntimeError("Detached preprocessing holders cannot set channels.")


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

    def prepare_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> PreparedPreprocessData: ...

    def prepare_resample(self, rate: float) -> PreparedPreprocessData: ...
    def prepare_normalization(self, method: str) -> PreparedPreprocessData: ...
    def prepare_rereference(
        self,
        channels: str | list[str],
    ) -> PreparedPreprocessData: ...
    def prepare_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> PreparedPreprocessData: ...
    def prepare_epoching(
        self,
        baseline: list[float] | tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int] | Sequence[str] | None,
        tmin: float,
        tmax: float,
        allow_boundary_drop: bool = False,
        *,
        event_label_aliases_by_source: Sequence[Mapping[str, str]] | None = None,
    ) -> PreparedPreprocessData: ...
    def commit_prepared(self, prepared: PreparedPreprocessData) -> bool: ...
    def detached_preparation_service(
        self,
        preprocessed_data: Sequence[Any],
    ) -> PreprocessStateService: ...


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

    def detached_preparation_service(
        self,
        preprocessed_data: Sequence[Any],
    ) -> PreprocessStateService:
        """Bind speculative processing to a captured source sequence."""
        return PreprocessStateService(
            _DetachedPreprocessStudy(preprocessed_data),
            processor_provider=self._processor_provider,
        )

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
        return self.commit_prepared(
            self.prepare_filter(l_freq, h_freq, notch_freqs),
        )

    def prepare_filter(
        self,
        l_freq: float | None,
        h_freq: float | None,
        notch_freqs: Sequence[float] | None = None,
    ) -> PreparedPreprocessData:
        return self._prepare_processor(
            self._processor("Filtering"),
            l_freq,
            h_freq,
            notch_freqs=notch_freqs,
            progress_stage="Filtering EEG recordings",
        )

    def apply_resample(self, rate: float) -> bool:
        return self.commit_prepared(self.prepare_resample(rate))

    def prepare_resample(self, rate: float) -> PreparedPreprocessData:
        return self._prepare_processor(
            self._processor("Resample"),
            rate,
            progress_stage="Resampling EEG recordings",
        )

    def apply_rereference(self, channels: str | list[str]) -> bool:
        return self.commit_prepared(self.prepare_rereference(channels))

    def prepare_rereference(
        self,
        channels: str | list[str],
    ) -> PreparedPreprocessData:
        return self._prepare_processor(
            self._processor("Rereference"),
            ref_channels=channels,
            progress_stage="Rereferencing EEG recordings",
        )

    def apply_normalization(self, method: str) -> bool:
        return self.commit_prepared(self.prepare_normalization(method))

    def prepare_normalization(self, method: str) -> PreparedPreprocessData:
        return self._prepare_processor(
            self._processor("Normalize"),
            norm=method,
            progress_stage="Normalizing EEG recordings",
        )

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
        return self.commit_prepared(
            self.prepare_standard_pipeline(
                l_freq=l_freq,
                h_freq=h_freq,
                notch_freq=notch_freq,
                rate=rate,
                ref_channels=ref_channels,
                normalization=normalization,
            )
        )

    def prepare_standard_pipeline(
        self,
        *,
        l_freq: float,
        h_freq: float,
        notch_freq: float | None = None,
        rate: float | None = None,
        ref_channels: str | list[str] | None = None,
        normalization: str | None = None,
    ) -> PreparedPreprocessData:
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")

        try:
            working_list = self._copy_working_list(data_list)
            working_list = self._process_working_list(
                working_list,
                self._processor("Filtering"),
                l_freq,
                h_freq,
                notch_freqs=None,
                progress_stage="Applying EEG bandpass filter",
            )
            if notch_freq:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Filtering"),
                    None,
                    None,
                    notch_freqs=[notch_freq],
                    progress_stage="Applying EEG notch filter",
                )
            if rate:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Resample"),
                    rate,
                    progress_stage="Resampling EEG recordings",
                )
            if ref_channels:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Rereference"),
                    ref_channels=ref_channels,
                    progress_stage="Rereferencing EEG recordings",
                )
            if normalization:
                working_list = self._process_working_list(
                    working_list,
                    self._processor("Normalize"),
                    norm=normalization,
                    progress_stage="Normalizing EEG recordings",
                )
        except OwnedOperationCancelledError:
            raise
        except Exception as exc:
            logger.error("Standard preprocessing pipeline failed: %s", exc)
            raise
        return PreparedPreprocessData(
            source_identity=self._data_identity(data_list),
            data=tuple(working_list),
        )

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
        return self.commit_prepared(
            self.prepare_epoching(
                baseline,
                selected_events,
                tmin,
                tmax,
                allow_boundary_drop,
                event_label_aliases_by_source=event_label_aliases_by_source,
            )
        )

    def prepare_epoching(
        self,
        baseline: list[float] | tuple[float | None, float | None] | None,
        selected_events: Mapping[str, int] | Sequence[str] | None,
        tmin: float,
        tmax: float,
        allow_boundary_drop: bool = False,
        *,
        event_label_aliases_by_source: Sequence[Mapping[str, str]] | None = None,
    ) -> PreparedPreprocessData:
        epoch_options: dict[str, Any] = {}
        if event_label_aliases_by_source is not None:
            epoch_options["event_label_aliases_by_source"] = (
                event_label_aliases_by_source
            )
        prepared = self._prepare_processor(
            self._processor("TimeEpoch"),
            baseline,
            selected_events,
            tmin,
            tmax,
            allow_boundary_drop,
            **epoch_options,
            progress_stage="Creating EEG epochs",
        )
        return PreparedPreprocessData(
            source_identity=prepared.source_identity,
            data=prepared.data,
            lock_dataset=True,
        )

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

    def commit_prepared(self, prepared: PreparedPreprocessData) -> bool:
        """Publish one prepared payload after final cancellation admission."""
        if not isinstance(prepared, PreparedPreprocessData):
            raise TypeError("prepared must be PreparedPreprocessData")
        current = self.study.preprocessed_data_list
        if self._data_identity(current) != prepared.source_identity:
            raise RuntimeError(
                "Preprocessed EEG state changed before prepared data could commit."
            )
        owned_work_commit_boundary(
            "Publishing preprocessed EEG data",
            completed=len(prepared.data),
            total=len(prepared.data),
        )
        self.study.set_preprocessed_data_list(
            list(prepared.data),
            force_update=True,
        )
        if prepared.lock_dataset:
            self.study.lock_dataset()
        self.publish_preprocess_changed()
        return True

    def _prepare_processor(
        self,
        processor_class: Any,
        *args: Any,
        progress_stage: str,
        **kwargs: Any,
    ) -> PreparedPreprocessData:
        data_list = self.study.preprocessed_data_list
        if not data_list:
            raise ValueError("No data to preprocess.")

        try:
            working_list = self._copy_working_list(data_list)
            owned_work_checkpoint(
                progress_stage,
                completed=0,
                total=len(working_list),
            )
            processor = processor_class(working_list)
            result = processor.data_preprocess(*args, **kwargs)
        except OwnedOperationCancelledError:
            raise
        except Exception as exc:
            logger.error("Preprocessing failed: %s", exc)
            raise
        return PreparedPreprocessData(
            source_identity=self._data_identity(data_list),
            data=tuple(result),
        )

    def _processor(self, name: str) -> Any:
        return self._processor_provider(name)

    @staticmethod
    def _process_working_list(
        working_list: list[Any],
        processor_class: Any,
        *args: Any,
        progress_stage: str,
        **kwargs: Any,
    ) -> list[Any]:
        owned_work_checkpoint(
            progress_stage,
            completed=0,
            total=len(working_list),
        )
        processor = processor_class(working_list)
        return list(processor.data_preprocess(*args, **kwargs))

    @staticmethod
    def _copy_working_list(data_list: list[Any]) -> list[Any]:
        working_list: list[Any] = []
        total = len(data_list)
        for index, data in enumerate(data_list):
            owned_work_checkpoint(
                "Copying EEG recordings for preprocessing",
                completed=index,
                total=total,
            )
            working_list.append(data.copy())
            owned_work_checkpoint(
                "Copying EEG recordings for preprocessing",
                completed=index + 1,
                total=total,
            )
        return working_list

    @staticmethod
    def _data_identity(data_list: Sequence[Any]) -> tuple[int, ...]:
        return tuple(id(data) for data in data_list)


__all__ = [
    "PreparedPreprocessData",
    "PreprocessProductPort",
    "PreprocessStateReadPort",
    "PreprocessStateService",
    "PreprocessStudyPort",
    "ProcessorProvider",
]
